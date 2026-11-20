"""
PROJETO: SolarGap Brasil
ARQUIVO: potencial/modelo.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 20/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Modelo explicativo da taxa de realização do potencial solar (TP4.5,
    Tarefa 4). Junta o alvo (potencial_municipal.parquet) aos fatores
    (fatores_municipais.parquet), compara uma Ridge padronizada com um LightGBM
    em validação cruzada agrupada por UF e explica o modelo escolhido com SHAP.

ALVO E AMOSTRA:
    taxa_realizacao da visão CORRIGIDA (padrão). Saem os municípios com
    flag_taxa_acima_1 (geração estimada acima do potencial técnico: telhado
    médio maior que o premissado, não adoção acima de 100%). Peso amostral =
    domicílios, para que municípios muito pequenos, cuja taxa oscila muito com
    poucas instalações, não dominem o ajuste nem as métricas.

SEM VAZAMENTO:
    As variáveis explicativas vêm só da Gold de fatores (Tarefa 3), que não usa
    a MMGD; conferir_sem_mmgd() barra nomes de colunas derivadas da MMGD.

VALIDAÇÃO:
    GroupKFold por UF (5 folds externos): nenhum município é testado com
    vizinhos da mesma UF no treino. A busca de hiperparâmetros é aninhada
    (GroupKFold interno de 3 folds, só nas UFs de treino) e a imputação da
    Ridge (mediana) é ajustada dentro do pipeline, só no treino de cada fold.
    O LightGBM trata ausentes nativamente e dispensa imputação.

SAÍDAS:
    data/processed/shap_municipal.parquet, data/processed/shap_uf.parquet,
    models/modelo_taxa_realizacao.joblib (não versionado) e figuras e tabelas
    em docs/potencial/.

EXECUÇÃO:
    python -m src.potencial.modelo
"""

from __future__ import annotations

import itertools
import json
import logging

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from lightgbm import LGBMRegressor
from matplotlib.colors import LinearSegmentedColormap
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.data_acquisition.coletor_base import configurar_logging
from src.potencial import config

# ═══════════════════ Definições ═══════════════════

# Alvo de cada visão da base ANEEL 10/2026 (ver atualizacao_base_10_2026.md)
ALVOS = {
    "corrigida": "taxa_realizacao",
    "aneel": "taxa_realizacao_aneel",
    "conservadora": "taxa_realizacao_conservador",
}
VISAO_PADRAO = "corrigida"
FLAG_EXCLUSAO = "flag_taxa_acima_1"
PESO = "domicilios"

# Fatores do modelo. Fora por redundância (seguem na matriz de correlação):
# icms_ano_inicio_isencao (espelho de icms_meses_isencao), area_km2 (log da
# área = log da população - log da densidade), populacao_2022 (log_populacao),
# n_distribuidoras e n_cooperativas (multi_distribuidora e cooperativa).
FATORES = [
    "renda_domiciliar_pc_media",
    "renda_domiciliar_pc_mediana",
    "pct_populacao_urbana",
    "pct_vab_agropecuaria",
    "tarifa_b1_rs_mwh",
    "multi_distribuidora",
    "cooperativa",
    "icms_meses_isencao",
    "irradiacao_kwh_m2_dia",
    "log_populacao",
    "log_densidade_hab_km2",
    "pct_area_agropecuaria",
]
FATORES_SO_CORRELACAO = ["icms_ano_inicio_isencao", "area_km2"]

# Prefixos de colunas derivadas da MMGD (ou do próprio alvo)
PREFIXOS_PROIBIDOS = (
    "kwp",
    "mmgd",
    "potencia",
    "n_unidades",
    "n_local",
    "n_potencia",
    "taxa_realizacao",
    "flag_",
    "y_",
    "x_",
    "gap",
)

N_FOLDS = 5
N_FOLDS_INTERNOS = 3
LIMIAR_CORRELACAO = 0.7
N_TOP = 5
COD_EXEMPLO = "4305108"  # Caxias do Sul (RS)
UF_ROBUSTEZ = "PR"  # UF da anomalia dos 75 kW (COPEL-DIS)

GRADES = {
    "ridge": {"alpha": [0.1, 1.0, 10.0, 100.0]},
    "lightgbm": {
        "num_leaves": [7, 15, 31],
        "n_estimators": [300, 600],
        "min_child_samples": [20, 60],
    },
}


# ═══════════════════ Base ═══════════════════


def conferir_sem_mmgd(colunas) -> None:
    """Falha se alguma variável explicativa tiver nome derivado da MMGD/alvo."""
    proibidas = [c for c in colunas if str(c).startswith(PREFIXOS_PROIBIDOS)]
    if proibidas:
        raise ValueError(f"Variáveis derivadas da MMGD entre os fatores: {proibidas}")


def preparar_fatores(fatores: pd.DataFrame) -> pd.DataFrame:
    """Fatores numéricos do modelo (booleanos 0/1, ausentes como NaN)."""
    f = fatores.copy()
    f["log_densidade_hab_km2"] = np.log(f["densidade_hab_km2"].astype(float))
    for col in ("multi_distribuidora", "cooperativa"):
        f[col] = f[col].astype("Float64").astype(float)
    return f


def montar_base(
    potencial: pd.DataFrame, fatores: pd.DataFrame, visao: str = VISAO_PADRAO
) -> tuple[pd.DataFrame, int]:
    """Junta alvo, peso e fatores; exclui flag_taxa_acima_1.

    Retorna (base com todos os municípios e a coluna usado_no_treino, n excluídos).
    A exclusão usa sempre a flag da visão corrigida, para que as três visões
    sejam comparadas na MESMA amostra (só o alvo muda).
    """
    conferir_sem_mmgd(FATORES)
    f = preparar_fatores(fatores)
    faltando = [c for c in FATORES if c not in f.columns]
    if faltando:
        raise KeyError(f"Fatores ausentes na Gold de fatores: {faltando}")

    alvo = potencial[["cod_ibge", "uf", PESO, FLAG_EXCLUSAO, ALVOS[visao]]].rename(
        columns={ALVOS[visao]: "alvo"}
    )
    base = alvo.merge(
        f[["cod_ibge", "nome", *FATORES, *FATORES_SO_CORRELACAO]],
        on="cod_ibge",
        how="inner",
        validate="one_to_one",
    )
    if len(base) != len(potencial):
        raise ValueError("Municípios do alvo sem linha na Gold de fatores")
    base["usado_no_treino"] = ~base[FLAG_EXCLUSAO] & base["alvo"].notna()
    return base, int(base[FLAG_EXCLUSAO].sum())


# ═══════════════════ Correlação ═══════════════════


def matriz_spearman(base: pd.DataFrame) -> pd.DataFrame:
    colunas = ["alvo", *FATORES, *FATORES_SO_CORRELACAO]
    treino = base.loc[base["usado_no_treino"], colunas].astype(float)
    return treino.corr(method="spearman")


def pares_fortes(
    matriz: pd.DataFrame, limiar: float = LIMIAR_CORRELACAO
) -> pd.DataFrame:
    """Pares distintos com |rho| > limiar, do mais forte ao mais fraco."""
    linhas = []
    for a, b in itertools.combinations(matriz.columns, 2):
        rho = matriz.loc[a, b]
        if abs(rho) > limiar:
            linhas.append({"variavel_1": a, "variavel_2": b, "rho": rho})
    pares = pd.DataFrame(linhas, columns=["variavel_1", "variavel_2", "rho"])
    return pares.reindex(pares["rho"].abs().sort_values(ascending=False).index)


def figura_correlacao(matriz: pd.DataFrame, caminho) -> None:
    # Divergente azul <-> vermelho com meio neutro cinza (rho = 0)
    cmap = LinearSegmentedColormap.from_list(
        "divergente", ["#2a78d6", "#f0efec", "#e34948"]
    )
    n = len(matriz)
    fig, ax = plt.subplots(figsize=(11, 9.5))
    im = ax.imshow(matriz.values, cmap=cmap, vmin=-1, vmax=1)
    ax.set_xticks(range(n), matriz.columns, rotation=55, ha="right", fontsize=8)
    ax.set_yticks(range(n), matriz.columns, fontsize=8)
    for i in range(n):
        for j in range(n):
            rho = matriz.iat[i, j]
            forte = i != j and abs(rho) > LIMIAR_CORRELACAO
            ax.text(
                j,
                i,
                f"{rho:.2f}",
                ha="center",
                va="center",
                fontsize=6.5,
                color="#1a1a19",
                fontweight="bold" if forte else "normal",
            )
            if forte:
                ax.add_patch(
                    plt.Rectangle(
                        (j - 0.5, i - 0.5),
                        1,
                        1,
                        fill=False,
                        edgecolor="#1a1a19",
                        lw=1.2,
                    )
                )
    for lado in ax.spines.values():
        lado.set_visible(False)
    fig.colorbar(im, ax=ax, shrink=0.8, label="rho de Spearman")
    ax.set_title(
        "Correlação de Spearman entre taxa de realização (alvo) e fatores\n"
        f"municípios do treino; contorno = |rho| > {LIMIAR_CORRELACAO}",
        fontsize=10,
        loc="left",
    )
    fig.tight_layout()
    fig.savefig(caminho, dpi=150, facecolor="#fcfcfb")
    plt.close(fig)


# ═══════════════════ Modelos ═══════════════════


def criar_modelo(tipo: str, params: dict):
    if tipo == "ridge":
        return Pipeline(
            [
                ("imputador", SimpleImputer(strategy="median")),
                ("padronizador", StandardScaler()),
                ("ridge", Ridge(**params)),
            ]
        )
    if tipo == "lightgbm":
        return LGBMRegressor(
            objective="regression",
            learning_rate=0.03,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.8,
            reg_lambda=1.0,
            random_state=config.SEMENTE,
            deterministic=True,
            force_col_wise=True,
            n_jobs=4,
            verbose=-1,
            **params,
        )
    raise ValueError(f"Tipo de modelo desconhecido: {tipo}")


def ajustar(tipo: str, params: dict, X: pd.DataFrame, y, w):
    modelo = criar_modelo(tipo, params)
    if tipo == "ridge":
        modelo.fit(X, y, padronizador__sample_weight=w, ridge__sample_weight=w)
    else:
        modelo.fit(X, y, sample_weight=w)
    return modelo


def metricas(y, previsto, w) -> dict:
    return {
        "r2_ponderado": r2_score(y, previsto, sample_weight=w),
        "mae_ponderado": mean_absolute_error(y, previsto, sample_weight=w),
        "r2": r2_score(y, previsto),
        "mae": mean_absolute_error(y, previsto),
    }


def combinacoes(grade: dict) -> list[dict]:
    chaves = list(grade)
    return [
        dict(zip(chaves, valores)) for valores in itertools.product(*grade.values())
    ]


def buscar_hiperparametros(
    tipo: str,
    X,
    y,
    w,
    grupos,
    n_folds: int = N_FOLDS_INTERNOS,
    grade: dict | None = None,
) -> tuple[dict, float]:
    """Melhor combinação pelo R² ponderado médio em GroupKFold (só nos dados dados)."""
    grade = grade or GRADES[tipo]
    folds = list(GroupKFold(n_splits=n_folds).split(X, y, grupos))
    melhor, melhor_r2 = None, -np.inf
    for params in combinacoes(grade):
        r2s = []
        for tr, te in folds:
            m = ajustar(tipo, params, X.iloc[tr], y[tr], w[tr])
            r2s.append(r2_score(y[te], m.predict(X.iloc[te]), sample_weight=w[te]))
        if np.mean(r2s) > melhor_r2:
            melhor, melhor_r2 = params, float(np.mean(r2s))
    return melhor, melhor_r2


def validacao_cruzada(
    tipo: str,
    X,
    y,
    w,
    grupos,
    n_folds: int = N_FOLDS,
    n_folds_internos: int = N_FOLDS_INTERNOS,
    grade: dict | None = None,
) -> pd.DataFrame:
    """CV externa agrupada por UF, com busca de hiperparâmetros aninhada."""
    linhas = []
    for i, (tr, te) in enumerate(GroupKFold(n_splits=n_folds).split(X, y, grupos), 1):
        params, _ = buscar_hiperparametros(
            tipo, X.iloc[tr], y[tr], w[tr], grupos[tr], n_folds_internos, grade
        )
        m = ajustar(tipo, params, X.iloc[tr], y[tr], w[tr])
        linhas.append(
            {
                "modelo": tipo,
                "fold": i,
                "ufs_teste": ",".join(sorted(set(grupos[te]))),
                "n_teste": len(te),
                **metricas(y[te], m.predict(X.iloc[te]), w[te]),
                "hiperparametros": json.dumps(params),
            }
        )
    return pd.DataFrame(linhas)


def resumir_cv(cv: pd.DataFrame) -> pd.DataFrame:
    return cv.groupby("modelo")[["r2_ponderado", "mae_ponderado", "r2", "mae"]].agg(
        ["mean", "std"]
    )


def escolher_modelo(cv: pd.DataFrame) -> str:
    """Maior R² ponderado médio fora da amostra; empate (< 0,005) -> menor MAE."""
    media = cv.groupby("modelo")[["r2_ponderado", "mae_ponderado"]].mean()
    ordem = media.sort_values("r2_ponderado", ascending=False)
    if (
        len(ordem) > 1
        and ordem["r2_ponderado"].iloc[0] - ordem["r2_ponderado"].iloc[1] < 0.005
    ):
        return str(ordem.iloc[:2]["mae_ponderado"].idxmin())
    return str(ordem.index[0])


# ═══════════════════ SHAP ═══════════════════


def explicar(tipo: str, modelo, X_explicar: pd.DataFrame, X_fundo: pd.DataFrame):
    """Retorna (valor_base, contribuições [n x fatores], previsão).

    LightGBM: TreeExplainer. Ridge: LinearExplainer no espaço imputado e
    padronizado, com o treino como fundo (contribuição = coef x (z - média)).
    """
    if tipo == "lightgbm":
        explainer = shap.TreeExplainer(modelo)
        valores = explainer.shap_values(X_explicar)
        base = float(np.ravel(explainer.expected_value)[0])
        previsao = modelo.predict(X_explicar)
    else:
        transformar = modelo[:-1]
        explainer = shap.LinearExplainer(
            modelo[-1],
            shap.maskers.Independent(
                transformar.transform(X_fundo), max_samples=len(X_fundo)
            ),
        )
        valores = explainer.shap_values(transformar.transform(X_explicar))
        base = float(np.ravel(explainer.expected_value)[0])
        previsao = modelo.predict(X_explicar)
    return base, np.asarray(valores), np.asarray(previsao)


def tabela_shap(
    base_dados: pd.DataFrame, valor_base: float, valores, previsao
) -> pd.DataFrame:
    shap_df = pd.DataFrame(valores, columns=[f"shap_{c}" for c in FATORES])
    shap_df.insert(0, "previsao", previsao)
    shap_df.insert(0, "valor_base", valor_base)
    shap_df.insert(0, "cod_ibge", base_dados["cod_ibge"].to_numpy())
    shap_df["alvo_observado"] = base_dados["alvo"].to_numpy()
    shap_df["usado_no_treino"] = base_dados["usado_no_treino"].to_numpy()
    return shap_df


def conferir_aditividade(shap_df: pd.DataFrame, tol: float = 1e-6) -> float:
    colunas = [f"shap_{c}" for c in FATORES]
    erro = (
        shap_df["valor_base"] + shap_df[colunas].sum(axis=1) - shap_df["previsao"]
    ).abs()
    if erro.max() > tol:
        raise ValueError(f"SHAP não aditivo: erro máximo {erro.max():.2e}")
    return float(erro.max())


def media_ponderada(df: pd.DataFrame, colunas, peso) -> pd.Series:
    w = df[peso].to_numpy(dtype=float)
    return pd.Series(
        {c: np.average(df[c].to_numpy(dtype=float), weights=w) for c in colunas}
    )


def shap_por_uf(shap_df: pd.DataFrame, base_dados: pd.DataFrame) -> pd.DataFrame:
    """Média ponderada por domicílios, só municípios do treino."""
    d = shap_df.merge(base_dados[["cod_ibge", "uf", PESO]], on="cod_ibge")
    d = d[d["usado_no_treino"]]
    colunas = [
        "valor_base",
        "previsao",
        "alvo_observado",
        *[f"shap_{c}" for c in FATORES],
    ]
    uf = d.groupby("uf").apply(
        lambda g: media_ponderada(g, colunas, PESO), include_groups=False
    )
    uf.insert(0, "n_municipios", d.groupby("uf").size())
    uf.insert(1, "domicilios", d.groupby("uf")[PESO].sum())
    return uf.reset_index()


def importancia(shap_df: pd.DataFrame, pesos) -> pd.Series:
    """Média de |SHAP| ponderada por domicílios, decrescente."""
    colunas = [f"shap_{c}" for c in FATORES]
    imp = pd.Series(
        np.average(np.abs(shap_df[colunas].to_numpy()), axis=0, weights=pesos),
        index=FATORES,
    )
    return imp.sort_values(ascending=False)


def sanidade_direcao(
    X: pd.DataFrame, shap_df: pd.DataFrame, fatores=None
) -> pd.DataFrame:
    """Spearman entre o valor do fator e a sua contribuição SHAP (> 0: mais fator -> mais taxa)."""
    fatores = fatores or [
        "renda_domiciliar_pc_media",
        "renda_domiciliar_pc_mediana",
        "tarifa_b1_rs_mwh",
    ]
    linhas = []
    for f in fatores:
        par = pd.DataFrame(
            {"v": X[f].to_numpy(), "s": shap_df[f"shap_{f}"].to_numpy()}
        ).dropna()
        rho = par["v"].corr(par["s"], method="spearman")
        linhas.append(
            {
                "fator": f,
                "rho_valor_shap": rho,
                "sentido": "positivo" if rho > 0 else "negativo",
            }
        )
    return pd.DataFrame(linhas)


def explicacao_exemplo(
    shap_df: pd.DataFrame, X: pd.DataFrame, cod: str
) -> pd.DataFrame:
    linha = shap_df.index[shap_df["cod_ibge"] == cod][0]
    contrib = pd.DataFrame(
        {
            "fator": FATORES,
            "valor": X.loc[linha, FATORES].to_numpy(),
            "contribuicao": shap_df.loc[linha, [f"shap_{c}" for c in FATORES]].to_numpy(
                dtype=float
            ),
        }
    )
    return contrib.reindex(
        contrib["contribuicao"].abs().sort_values(ascending=False).index
    )


def figuras_shap(
    shap_df,
    X,
    pesos,
    valor_base,
    caminho_beeswarm,
    caminho_waterfall,
    cod_exemplo,
    nome_exemplo,
):
    """Beeswarm (municípios do treino, ordem = importância ponderada) e waterfall do exemplo."""
    colunas = [f"shap_{c}" for c in FATORES]
    treino = shap_df["usado_no_treino"].to_numpy()
    imp = importancia(shap_df[treino], pesos[treino])
    ordem = np.array([FATORES.index(f) for f in imp.index])
    exp = shap.Explanation(
        values=shap_df.loc[treino, colunas].to_numpy(dtype=float),
        base_values=np.full(treino.sum(), valor_base),
        data=X.loc[treino, FATORES].to_numpy(dtype=float),
        feature_names=FATORES,
    )
    plt.figure()
    shap.plots.beeswarm(exp, max_display=len(FATORES), order=ordem, show=False)
    plt.title(
        "SHAP: contribuição de cada fator para a taxa de realização\n"
        "ordem = média de |SHAP| ponderada por domicílios",
        fontsize=10,
        loc="left",
    )
    plt.tight_layout()
    plt.savefig(caminho_beeswarm, dpi=150, bbox_inches="tight", facecolor="#fcfcfb")
    plt.close("all")

    i = shap_df.index[shap_df["cod_ibge"] == cod_exemplo][0]
    exp_i = shap.Explanation(
        values=shap_df.loc[i, colunas].to_numpy(dtype=float),
        base_values=valor_base,
        data=X.loc[i, FATORES].to_numpy(dtype=float).round(3),
        feature_names=FATORES,
    )
    plt.figure()
    shap.plots.waterfall(exp_i, max_display=len(FATORES), show=False)
    plt.title(f"SHAP: {nome_exemplo} ({cod_exemplo})", fontsize=10, loc="left")
    plt.tight_layout()
    plt.savefig(caminho_waterfall, dpi=150, bbox_inches="tight", facecolor="#fcfcfb")
    plt.close("all")


# ═══════════════════ Robustez ═══════════════════


def robustez_visoes(
    potencial,
    fatores,
    tipo: str,
    params: dict,
    n_top: int = N_TOP,
    uf: str = UF_ROBUSTEZ,
) -> pd.DataFrame:
    """Reajusta o modelo final (mesmos hiperparâmetros, mesma amostra) em cada visão."""
    linhas = []
    for visao in ALVOS:
        base, _ = montar_base(potencial, fatores, visao)
        treino = base[base["usado_no_treino"]].reset_index(drop=True)
        X, y, w = (
            treino[FATORES],
            treino["alvo"].to_numpy(),
            treino[PESO].to_numpy(float),
        )
        grupos = treino["uf"].to_numpy()
        r2s = []
        for tr, te in GroupKFold(n_splits=N_FOLDS).split(X, y, grupos):
            m = ajustar(tipo, params, X.iloc[tr], y[tr], w[tr])
            r2s.append(r2_score(y[te], m.predict(X.iloc[te]), sample_weight=w[te]))
        modelo = ajustar(tipo, params, X, y, w)
        vb, valores, prev = explicar(tipo, modelo, X, X)
        shap_df = tabela_shap(treino, vb, valores, prev)
        imp = importancia(shap_df, w)
        no_uf = (treino["uf"] == uf).to_numpy()
        shap_uf = media_ponderada(
            shap_df[no_uf].assign(peso=w[no_uf]), [f"shap_{c}" for c in FATORES], "peso"
        )
        for rank, (fator, valor) in enumerate(imp.items(), 1):
            linhas.append(
                {
                    "visao": visao,
                    "fator": fator,
                    "rank": rank,
                    "importancia_media_abs": valor,
                    f"shap_medio_{uf.lower()}": shap_uf[f"shap_{fator}"],
                    "r2_ponderado_cv_hiperparametros_fixos": float(np.mean(r2s)),
                    f"alvo_medio_{uf.lower()}": np.average(y[no_uf], weights=w[no_uf]),
                    f"previsao_media_{uf.lower()}": np.average(
                        prev[no_uf], weights=w[no_uf]
                    ),
                    "n_alvo_acima_1": int((y > 1).sum()),
                }
            )
    return pd.DataFrame(linhas)


# ═══════════════════ Orquestração ═══════════════════


def construir_modelo() -> dict:
    configurar_logging("POTENCIAL_MODELO", config.PASTA_LOGS)
    config.PASTA_DOCS_POTENCIAL.mkdir(parents=True, exist_ok=True)
    config.PASTA_MODELOS.mkdir(parents=True, exist_ok=True)

    potencial = pd.read_parquet(config.ARQUIVO_GOLD_MUNICIPAL)
    fatores = pd.read_parquet(config.ARQUIVO_GOLD_FATORES)

    # 1. Base
    base, n_excluidos = montar_base(potencial, fatores, VISAO_PADRAO)
    treino = base[base["usado_no_treino"]].reset_index(drop=True)
    logging.info(
        "Municípios excluídos por %s: %d; no treino: %d",
        FLAG_EXCLUSAO,
        n_excluidos,
        len(treino),
    )
    logging.info("Fatores (nenhum derivado da MMGD): %s", FATORES)
    X, y = treino[FATORES], treino["alvo"].to_numpy()
    w, grupos = treino[PESO].to_numpy(float), treino["uf"].to_numpy()
    logging.info(
        "Ausentes no treino:\n%s", X.isna().sum()[X.isna().sum() > 0].to_string()
    )

    # 2. Correlação
    matriz = matriz_spearman(base)
    matriz.round(4).to_csv(config.ARQUIVO_CORRELACAO_CSV, encoding="utf-8")
    figura_correlacao(matriz, config.ARQUIVO_CORRELACAO_PNG)
    pares = pares_fortes(matriz)
    logging.info(
        "Pares com |rho| > %.1f:\n%s",
        LIMIAR_CORRELACAO,
        pares.round(3).to_string(index=False),
    )

    # 3-4. Validação cruzada agrupada por UF
    cv = pd.concat(
        [validacao_cruzada(t, X, y, w, grupos) for t in GRADES], ignore_index=True
    )
    cv.to_csv(config.ARQUIVO_METRICAS_CV, index=False, encoding="utf-8")
    logging.info("Validação cruzada por fold:\n%s", cv.round(4).to_string(index=False))
    logging.info("Resumo (média e desvio):\n%s", resumir_cv(cv).round(4).to_string())
    tipo = escolher_modelo(cv)

    # Modelo final: busca em toda a amostra (GroupKFold de 5) e reajuste completo
    params, r2_busca = buscar_hiperparametros(tipo, X, y, w, grupos, n_folds=N_FOLDS)
    modelo = ajustar(tipo, params, X, y, w)
    logging.info(
        "Modelo escolhido: %s %s (R² ponderado na busca final: %.4f)",
        tipo,
        params,
        r2_busca,
    )
    joblib.dump(
        {
            "tipo": tipo,
            "params": params,
            "modelo": modelo,
            "fatores": FATORES,
            "alvo": ALVOS[VISAO_PADRAO],
            "semente": config.SEMENTE,
        },
        config.ARQUIVO_MODELO,
    )
    ridge_final = ajustar(
        "ridge", buscar_hiperparametros("ridge", X, y, w, grupos, N_FOLDS)[0], X, y, w
    )
    coefs_ridge = pd.Series(ridge_final[-1].coef_, index=FATORES)

    # 5. SHAP para todos os municípios (os excluídos ficam marcados)
    X_todos = base[FATORES]
    vb, valores, prev = explicar(tipo, modelo, X_todos, X)
    shap_df = tabela_shap(base, vb, valores, prev)
    erro = conferir_aditividade(shap_df)
    logging.info("Aditividade do SHAP: erro máximo %.2e", erro)
    shap_df.to_parquet(config.ARQUIVO_GOLD_SHAP_MUNICIPAL, index=False)
    shap_uf = shap_por_uf(shap_df, base)
    shap_uf.to_parquet(config.ARQUIVO_GOLD_SHAP_UF, index=False)
    nome_exemplo = base.loc[base["cod_ibge"] == COD_EXEMPLO, "nome"].iloc[0]
    figuras_shap(
        shap_df,
        X_todos,
        base[PESO].to_numpy(float),
        vb,
        config.ARQUIVO_SHAP_BEESWARM,
        config.ARQUIVO_SHAP_WATERFALL,
        COD_EXEMPLO,
        nome_exemplo,
    )
    no_treino = shap_df["usado_no_treino"].to_numpy()
    imp = importancia(shap_df[no_treino], treino[PESO].to_numpy(float))
    logging.info("Importância (média |SHAP| ponderada):\n%s", imp.round(5).to_string())
    exemplo = explicacao_exemplo(shap_df, X_todos, COD_EXEMPLO)
    linha_ex = shap_df[shap_df["cod_ibge"] == COD_EXEMPLO].iloc[0]
    logging.info(
        "%s: base %.4f, previsão %.4f, observado %.4f\n%s",
        nome_exemplo,
        vb,
        linha_ex["previsao"],
        linha_ex["alvo_observado"],
        exemplo.round(4).to_string(index=False),
    )

    # 6. Robustez à anomalia dos 75 kW
    robustez = robustez_visoes(potencial, fatores, tipo, params)
    robustez.to_csv(config.ARQUIVO_ROBUSTEZ_CSV, index=False, encoding="utf-8")
    logging.info(
        "Robustez (top %d):\n%s",
        N_TOP,
        robustez[robustez["rank"] <= N_TOP].round(4).to_string(index=False),
    )

    # 7. Sanidade de direção
    sanidade = sanidade_direcao(
        X_todos[no_treino].reset_index(drop=True),
        shap_df[no_treino].reset_index(drop=True),
    )
    sanidade["coef_ridge_padronizado"] = sanidade["fator"].map(coefs_ridge)
    sanidade["rho_spearman_alvo"] = sanidade["fator"].map(matriz["alvo"])
    logging.info("Sanidade de direção:\n%s", sanidade.round(4).to_string(index=False))

    return {
        "n_excluidos": n_excluidos,
        "n_treino": len(treino),
        "pares": pares,
        "cv": cv,
        "tipo": tipo,
        "params": params,
        "importancia": imp,
        "exemplo": exemplo,
        "linha_exemplo": linha_ex,
        "valor_base": vb,
        "robustez": robustez,
        "sanidade": sanidade,
        "coefs_ridge": coefs_ridge,
        "erro_aditividade": erro,
    }


if __name__ == "__main__":
    construir_modelo()
