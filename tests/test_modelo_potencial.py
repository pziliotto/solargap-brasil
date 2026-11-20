"""Testes do modelo explicativo da taxa de realização (TP4.5, Tarefa 4).

Dados sintéticos: não dependem de data/raw, data/interim nem de rede.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.potencial import config
from src.potencial import modelo as m

UFS = ["AC", "BA", "GO", "MG", "PR", "RS", "SC", "SP"]
GRADE_PEQUENA = {
    "ridge": {"alpha": [1.0, 10.0]},
    "lightgbm": {"num_leaves": [7], "n_estimators": [50], "min_child_samples": [10]},
}


def dados_sinteticos(
    n: int = 400, semente: int = 0
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(semente)
    cod = [f"{1000000 + i}" for i in range(n)]
    renda = rng.lognormal(7, 0.4, n)
    densidade = rng.lognormal(3, 1.2, n)
    tarifa = rng.normal(740, 80, n)
    taxa = np.clip(
        0.05
        + 0.00008 * renda
        - 0.02 * np.log(densidade)
        + 0.0002 * (tarifa - 740)
        + rng.normal(0, 0.03, n),
        0,
        None,
    )
    taxa[:3] = [1.4, 1.2, 1.1]  # municípios acima do potencial
    fatores = pd.DataFrame(
        {
            "cod_ibge": cod,
            "nome": [f"Município {i}" for i in range(n)],
            "renda_domiciliar_pc_media": renda,
            "renda_domiciliar_pc_mediana": renda * rng.uniform(0.6, 0.8, n),
            "pct_populacao_urbana": rng.uniform(20, 100, n),
            "pct_vab_agropecuaria": rng.uniform(0, 60, n),
            "tarifa_b1_rs_mwh": tarifa,
            "multi_distribuidora": pd.array(rng.random(n) < 0.1, dtype="boolean"),
            "cooperativa": pd.array(rng.random(n) < 0.1, dtype="boolean"),
            "icms_meses_isencao": rng.integers(90, 130, n),
            "icms_ano_inicio_isencao": rng.integers(2015, 2019, n),
            "irradiacao_kwh_m2_dia": rng.uniform(4, 6, n),
            "log_populacao": rng.normal(9, 1, n),
            "densidade_hab_km2": densidade,
            "area_km2": rng.lognormal(6, 1, n),
            "pct_area_agropecuaria": rng.uniform(0, 90, n),
        }
    )
    fatores.loc[5, "tarifa_b1_rs_mwh"] = np.nan  # ausentes, como na Gold real
    fatores.loc[6, "cooperativa"] = pd.NA
    potencial = pd.DataFrame(
        {
            "cod_ibge": cod,
            "uf": [UFS[i % len(UFS)] for i in range(n)],
            "domicilios": rng.integers(300, 50000, n),
            "taxa_realizacao": taxa,
            "taxa_realizacao_aneel": taxa * 1.05,
            "taxa_realizacao_conservador": taxa * 1.02,
            "flag_taxa_acima_1": taxa > 1,
        }
    )
    return potencial, fatores


@pytest.fixture(scope="module")
def base_treino():
    potencial, fatores = dados_sinteticos()
    base, n_excl = m.montar_base(potencial, fatores)
    treino = base[base["usado_no_treino"]].reset_index(drop=True)
    return base, treino, n_excl


def xyw(treino):
    return (
        treino[m.FATORES],
        treino["alvo"].to_numpy(),
        treino["domicilios"].to_numpy(float),
        treino["uf"].to_numpy(),
    )


# ── Base e vazamento ──


def test_montar_base_exclui_flag_e_conta(base_treino):
    base, treino, n_excl = base_treino
    assert n_excl == 3
    assert len(base) == 400 and len(treino) == 397
    assert (treino["alvo"] <= 1).all()
    assert treino["multi_distribuidora"].dtype == float
    assert treino["log_densidade_hab_km2"].notna().all()


def test_fatores_nao_derivam_da_mmgd():
    m.conferir_sem_mmgd(m.FATORES)
    with pytest.raises(ValueError, match="MMGD"):
        m.conferir_sem_mmgd([*m.FATORES, "kwp_total"])
    with pytest.raises(ValueError):
        m.conferir_sem_mmgd(["taxa_realizacao_aneel"])


def test_montar_base_falha_se_faltar_municipio_nos_fatores():
    potencial, fatores = dados_sinteticos()
    with pytest.raises(ValueError):
        m.montar_base(potencial, fatores.iloc[1:])


def test_visoes_usam_a_mesma_amostra():
    potencial, fatores = dados_sinteticos()
    amostras = {
        v: set(b.loc[b["usado_no_treino"], "cod_ibge"])
        for v in m.ALVOS
        for b in [m.montar_base(potencial, fatores, v)[0]]
    }
    assert amostras["corrigida"] == amostras["aneel"] == amostras["conservadora"]


# ── Correlação ──


def test_pares_fortes_respeita_limiar():
    matriz = pd.DataFrame(
        [[1, 0.9, -0.75], [0.9, 1, 0.1], [-0.75, 0.1, 1]],
        index=list("abc"),
        columns=list("abc"),
    )
    pares = m.pares_fortes(matriz, 0.7)
    assert list(zip(pares["variavel_1"], pares["variavel_2"])) == [
        ("a", "b"),
        ("a", "c"),
    ]


# ── Validação cruzada ──


def test_cv_agrupada_por_uf_nao_mistura_ufs(base_treino):
    _, treino, _ = base_treino
    X, y, w, g = xyw(treino)
    cv = m.validacao_cruzada(
        "ridge", X, y, w, g, n_folds=4, n_folds_internos=2, grade=GRADE_PEQUENA["ridge"]
    )
    ufs_por_fold = [set(s.split(",")) for s in cv["ufs_teste"]]
    assert set().union(*ufs_por_fold) == set(UFS)
    assert sum(len(u) for u in ufs_por_fold) == len(UFS)  # cada UF em um só fold
    assert cv["n_teste"].sum() == len(treino)


def test_pipeline_ridge_e_lightgbm_aceitam_ausentes_e_aprendem(base_treino):
    _, treino, _ = base_treino
    X, y, w, g = xyw(treino)
    assert X.isna().any().any()
    for tipo in ("ridge", "lightgbm"):
        cv = m.validacao_cruzada(
            tipo, X, y, w, g, n_folds=4, n_folds_internos=2, grade=GRADE_PEQUENA[tipo]
        )
        assert cv["r2_ponderado"].mean() > 0.3, tipo


def test_imputacao_ajustada_so_no_treino(base_treino):
    _, treino, _ = base_treino
    X, y, w, _ = xyw(treino)
    parte = X.iloc[:200]
    pipe = m.ajustar("ridge", {"alpha": 1.0}, parte, y[:200], w[:200])
    mediana_tarifa = pipe.named_steps["imputador"].statistics_[
        m.FATORES.index("tarifa_b1_rs_mwh")
    ]
    assert mediana_tarifa == pytest.approx(parte["tarifa_b1_rs_mwh"].median())
    assert mediana_tarifa != pytest.approx(X["tarifa_b1_rs_mwh"].median())


def test_lightgbm_com_semente_fixa_e_deterministico(base_treino):
    _, treino, _ = base_treino
    X, y, w, _ = xyw(treino)
    params = GRADE_PEQUENA["lightgbm"]
    params = {k: v[0] for k, v in params.items()}
    p1 = m.ajustar("lightgbm", params, X, y, w).predict(X)
    p2 = m.ajustar("lightgbm", params, X, y, w).predict(X)
    np.testing.assert_array_equal(p1, p2)


def test_escolher_modelo_pela_metrica_fora_da_amostra():
    cv = pd.DataFrame(
        {
            "modelo": ["ridge", "ridge", "lightgbm", "lightgbm"],
            "r2_ponderado": [0.20, 0.30, 0.35, 0.45],
            "mae_ponderado": [0.05, 0.05, 0.06, 0.06],
        }
    )
    assert m.escolher_modelo(cv) == "lightgbm"
    empate = cv.assign(r2_ponderado=[0.30, 0.30, 0.30, 0.302])
    assert m.escolher_modelo(empate) == "ridge"  # empate de R² -> menor MAE


# ── SHAP ──


@pytest.mark.parametrize("tipo", ["lightgbm", "ridge"])
def test_shap_aditivo(base_treino, tipo):
    base, treino, _ = base_treino
    X, y, w, _ = xyw(treino)
    params = {k: v[0] for k, v in GRADE_PEQUENA[tipo].items()}
    modelo = m.ajustar(tipo, params, X, y, w)
    vb, valores, prev = m.explicar(tipo, modelo, base[m.FATORES], X)
    shap_df = m.tabela_shap(base, vb, valores, prev)
    assert list(shap_df.columns[:3]) == ["cod_ibge", "valor_base", "previsao"]
    assert len(shap_df) == len(base)
    assert m.conferir_aditividade(shap_df) < 1e-6
    np.testing.assert_allclose(prev, modelo.predict(base[m.FATORES]))


def test_conferir_aditividade_detecta_erro():
    linha = {"cod_ibge": "1", "valor_base": 0.1, "previsao": 0.5}
    linha.update({f"shap_{f}": 0.0 for f in m.FATORES})
    with pytest.raises(ValueError, match="aditivo"):
        m.conferir_aditividade(pd.DataFrame([linha]))


def test_shap_por_uf_e_media_ponderada_por_domicilios():
    base = pd.DataFrame(
        {
            "cod_ibge": ["1", "2", "3"],
            "uf": ["PR", "PR", "SC"],
            "domicilios": [100, 300, 50],
        }
    )
    shap_df = pd.DataFrame(
        {
            "cod_ibge": ["1", "2", "3"],
            "valor_base": 0.1,
            "previsao": [0.2, 0.4, 0.3],
            "alvo_observado": [0.2, 0.4, 0.3],
            "usado_no_treino": [True, True, True],
            **{f"shap_{f}": [0.0, 0.0, 0.0] for f in m.FATORES},
        }
    )
    shap_df["shap_tarifa_b1_rs_mwh"] = [0.1, 0.3, -0.2]
    uf = m.shap_por_uf(shap_df, base).set_index("uf")
    assert uf.loc["PR", "shap_tarifa_b1_rs_mwh"] == pytest.approx(
        (0.1 * 100 + 0.3 * 300) / 400
    )
    assert uf.loc["PR", "domicilios"] == 400 and uf.loc["SC", "n_municipios"] == 1


def test_sanidade_direcao_detecta_sentido(base_treino):
    _base, treino, _ = base_treino
    X, y, w, _ = xyw(treino)
    modelo = m.ajustar("ridge", {"alpha": 1.0}, X, y, w)
    vb, valores, prev = m.explicar("ridge", modelo, X, X)
    sanidade = m.sanidade_direcao(X, m.tabela_shap(treino, vb, valores, prev))
    sentido = sanidade.set_index("fator")["sentido"]
    # no gerador sintético, renda e tarifa aumentam a taxa
    assert sentido["renda_domiciliar_pc_media"] == "positivo"
    assert sentido["tarifa_b1_rs_mwh"] == "positivo"


# ── Saídas reais (rodam se o modelo já foi gerado) ──


@pytest.mark.skipif(
    not config.ARQUIVO_GOLD_SHAP_MUNICIPAL.exists(),
    reason="shap_municipal.parquet não gerado",
)
def test_gold_shap_real_aditiva_e_completa():
    shap_df = pd.read_parquet(config.ARQUIVO_GOLD_SHAP_MUNICIPAL)
    assert len(shap_df) == config.TOTAL_MUNICIPIOS
    assert not shap_df["cod_ibge"].duplicated().any()
    assert m.conferir_aditividade(shap_df) < 1e-6
    assert (~shap_df["usado_no_treino"]).sum() == 19
    uf = pd.read_parquet(config.ARQUIVO_GOLD_SHAP_UF)
    assert len(uf) == 27
