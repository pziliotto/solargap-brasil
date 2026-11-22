"""
PROJETO: SolarGap Brasil
ARQUIVO: potencial.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026

DESCRIÇÃO:
    Regra de negócio do potencial solar municipal (TP4.5, Tarefa 7),
    compartilhada pela página "Potencial Solar" do painel e pelas rotas
    /potencial da API. Mesmo padrão de indicadores.py: pandas puro, sem
    Streamlit nem FastAPI, para que painel e API mostrem os mesmos números.

FONTES (camada Gold, só leitura):
    potencial_municipal.parquet, potencial_uf.parquet  Tarefa 2 (x, y, gap, taxa)
    fatores_municipais.parquet                         Tarefa 3 (fatores)
    shap_municipal.parquet                             Tarefa 4 (contribuições SHAP)
    projecao_irradiacao_{municipal,uf}.parquet         Tarefa 6 (cenários 2030–2050)
    docs/potencial/matriz_correlacao.csv               Tarefa 4 (Spearman)
    docs/potencial/robustez_visoes.csv                 Tarefa 4 (ranking por visão)

DEFINIÇÕES:
    x    potencial técnico residencial (MWh/ano): domicílios x 15 m² úteis de
         telhado x eficiência 20% x irradiação x PR 0,75 x 365
    y    produção estimada da MMGD Residencial + Rural com geração na própria UC
    gap  x - y;  taxa de realização (% realizado) = y / x

VISÕES (mesmas chaves de indicadores.VISOES):
    corrigida (padrão), aneel e conservadora mudam só y, gap e taxa; x não
    depende da base da ANEEL. Nas agregações (UF, Brasil), a taxa é Σy / Σx,
    nunca a média das taxas municipais.

SHAP E VISÃO:
    O modelo explicativo foi treinado no alvo da visão corrigida (Tarefa 4) e
    é o único com contribuições por município na Gold. Nas outras visões, a
    explicação devolve as mesmas contribuições, a taxa observada da visão
    pedida e o ranking global de fatores dela (robustez_visoes.csv), com um
    aviso explícito. Associação, não causalidade: o SHAP descreve como o
    modelo usa cada fator, não o efeito de mudá-lo.

CENÁRIOS (Tarefa 6):
    A projeção muda só a irradiação, com a potência instalada fixa. A Gold tem
    y projetado das visões corrigida e ANEEL; o da conservadora é derivado aqui
    pela mesma razão: y_proj = y x (y_proj / y) da visão corrigida. No
    município a razão é exatamente 1 + delta, porque H se cancela; na UF é uma
    aproximação de diferença desprezível (pondera a irradiação pelo kWp
    corrigido, e não pelo conservador).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.data_acquisition.coletor_base import obter_project_root
from src.preparacao import esquema
from src.servicos.dados import PASTA_PROCESSED, DadosIndisponiveis
from src.servicos.indicadores import VISAO_PADRAO, normalizar_visao

PROJECT_ROOT = obter_project_root(__file__)
PASTA_DOCS_POTENCIAL = PROJECT_ROOT / "docs" / "potencial"
PASTA_MALHAS = PROJECT_ROOT / "data" / "external" / "malhas"

ARQUIVOS = {
    "municipal": "potencial_municipal.parquet",
    "uf": "potencial_uf.parquet",
    "fatores": "fatores_municipais.parquet",
    "shap": "shap_municipal.parquet",
    "projecao_municipal": "projecao_irradiacao_municipal.parquet",
    "projecao_uf": "projecao_irradiacao_uf.parquet",
}
ARQUIVO_CORRELACAO = "matriz_correlacao.csv"
ARQUIVO_ROBUSTEZ = "robustez_visoes.csv"

# Premissas da Tarefa 2 (src/potencial/config.py), repetidas aqui para a nota
# de metodologia sem importar a pilha do pipeline.
PREMISSAS = {
    "performance_ratio": 0.75,
    "eficiencia_painel": 0.20,
    "area_util_telhado_m2": 15,
    "areas_sensibilidade_m2": [10, 15, 20],
    "base_aneel": f"10/{esquema.ANO_PARCIAL} ({esquema.ANO_PARCIAL} parcial, até outubro)",
}

# Colunas da Gold de potencial por visão: y e taxa.
COLUNAS_VISAO = {
    "corrigida": {"y": "y_mwh_ano", "taxa": "taxa_realizacao"},
    "aneel": {"y": "y_aneel_mwh_ano", "taxa": "taxa_realizacao_aneel"},
    "conservadora": {
        "y": "y_conservador_mwh_ano",
        "taxa": "taxa_realizacao_conservador",
    },
}
# Prefixo do y projetado na Gold da Tarefa 6 (None: derivado da corrigida).
Y_PROJETADO_GOLD = {"corrigida": "y", "aneel": "y_aneel", "conservadora": None}
GAP_PROJETADO_GOLD = {"corrigida": "gap", "aneel": "gap_aneel", "conservadora": None}

NA_VISAO = {
    "corrigida": "na visão corrigida",
    "aneel": "no critério ANEEL",
    "conservadora": "no limite conservador",
}
AVISO_CENARIOS = (
    "Cenário com faixa de incerteza, não previsão. Muda só a irradiação (NEX-GDDP-CMIP6, "
    "5 modelos, método delta sobre a NASA POWER 2023–2025), com a potência instalada "
    "fixa no valor atual; a taxa de realização do município não muda, porque a "
    "irradiação se cancela em y / x. Metodologia: docs/potencial/README.md, seção "
    "Projeção 2030–2050."
)
CENARIOS = {"ssp245": "SSP2-4.5 (intermediário)", "ssp585": "SSP5-8.5 (emissões altas)"}
JANELAS = ("2030-2039", "2040-2050")

# ═══════════════════ Fatores em linguagem simples ═══════════════════


@dataclass(frozen=True)
class Fator:
    rotulo: str
    coluna_valor: str  # coluna exibida (ex.: densidade, e não o log da densidade)
    formato: str  # "{}" recebe o número já formatado
    casas: int = 0
    booleano: bool = False


FATORES = {
    "log_densidade_hab_km2": Fator(
        "Densidade demográfica", "densidade_hab_km2", "{} hab/km²", 1
    ),
    "renda_domiciliar_pc_media": Fator(
        "Renda domiciliar per capita (média)", "renda_domiciliar_pc_media", "R$ {}/mês"
    ),
    "renda_domiciliar_pc_mediana": Fator(
        "Renda domiciliar per capita (mediana)",
        "renda_domiciliar_pc_mediana",
        "R$ {}/mês",
    ),
    "pct_vab_agropecuaria": Fator(
        "Peso da agropecuária na economia (VAB)", "pct_vab_agropecuaria", "{}%", 1
    ),
    "tarifa_b1_rs_mwh": Fator(
        "Tarifa de energia residencial B1", "tarifa_b1_rs_mwh", "R$ {}/MWh"
    ),
    "irradiacao_kwh_m2_dia": Fator(
        "Irradiação solar", "irradiacao_kwh_m2_dia", "{} kWh/m²/dia", 2
    ),
    "pct_area_agropecuaria": Fator(
        "Área ocupada pela agropecuária", "pct_area_agropecuaria", "{}% da área", 1
    ),
    "log_populacao": Fator("População", "populacao_2022", "{} habitantes"),
    "pct_populacao_urbana": Fator("População urbana", "pct_populacao_urbana", "{}%", 1),
    "icms_meses_isencao": Fator(
        "Tempo de isenção de ICMS na geração distribuída",
        "icms_meses_isencao",
        "{} meses",
    ),
    "multi_distribuidora": Fator(
        "Atendido por mais de uma distribuidora",
        "multi_distribuidora",
        "{}",
        booleano=True,
    ),
    "cooperativa": Fator(
        "Atendido por cooperativa de eletrificação",
        "cooperativa",
        "{}",
        booleano=True,
    ),
}
COLUNAS_SHAP = [f"shap_{f}" for f in FATORES]

# Famílias de variáveis que medem a mesma coisa por ângulos diferentes e,
# correlacionadas, dividem o crédito do SHAP de forma arbitrária (renda média
# e mediana: ρ = 0,98; mais de uma distribuidora e cooperativa: ρ = 0,84).
# Como o SHAP é aditivo, a contribuição do grupo é a soma das contribuições.
# Valor: (rótulo do grupo, {fator: rótulo do fator dentro do grupo}).
GRUPOS = {
    "renda": (
        "Renda",
        {
            "renda_domiciliar_pc_media": "média",
            "renda_domiciliar_pc_mediana": "mediana",
        },
    ),
    "agropecuaria": (
        "Agropecuária",
        {
            "pct_vab_agropecuaria": "peso na economia (VAB)",
            "pct_area_agropecuaria": "área ocupada",
        },
    ),
    "distribuicao": (
        "Distribuidora e cooperativa",
        {
            "multi_distribuidora": "mais de uma distribuidora",
            "cooperativa": "cooperativa de eletrificação",
        },
    ),
}
# Fatores fora das famílias formam um grupo próprio, com o mesmo rótulo.
GRUPO_DO_FATOR = {
    fator: grupo for grupo, (_, membros) in GRUPOS.items() for fator in membros
} | {
    fator: fator for fator in FATORES if not any(fator in m for _, m in GRUPOS.values())
}

# Na leitura em linguagem simples: até 3 grupos por sinal, com pelo menos 1 p.p.
N_GRUPOS_LEITURA = 3
LIMIAR_LEITURA_PP = 1.0
# Diferença observada x prevista abaixo disso (em p.p.) é "em linha".
TOLERANCIA_ESPERADO_PP = 0.5


def rotulo_grupo(grupo: str) -> str:
    return GRUPOS[grupo][0] if grupo in GRUPOS else FATORES[grupo].rotulo


def rotulo_no_grupo(fator: str) -> str:
    """Rótulo do fator para o waterfall: 'Renda · média' ou o rótulo próprio."""
    grupo = GRUPO_DO_FATOR[fator]
    if grupo in GRUPOS:
        return f"{GRUPOS[grupo][0]} · {GRUPOS[grupo][1][fator]}"
    return FATORES[fator].rotulo


class RecorteInexistente(LookupError):
    """Município ou UF sem registro na Gold (a API responde 404)."""


# ═══════════════════ Carga ═══════════════════


@dataclass
class BasePotencial:
    municipal: pd.DataFrame
    uf: pd.DataFrame
    fatores: pd.DataFrame
    shap: pd.DataFrame
    projecao_municipal: pd.DataFrame
    projecao_uf: pd.DataFrame
    correlacao: pd.DataFrame
    robustez: pd.DataFrame


def _ler_parquet(caminho: Path) -> pd.DataFrame:
    if not caminho.exists():
        raise DadosIndisponiveis(
            f"Arquivo da Gold de potencial não encontrado: {caminho.name}. "
            "Rode o pipeline de src/potencial ou restaure o arquivo do repositório."
        )
    try:
        tabela = pd.read_parquet(caminho)
    except Exception as erro:  # qualquer falha de leitura vira 503
        raise DadosIndisponiveis(f"Falha ao ler {caminho.name}: {erro}") from erro
    if "cod_ibge" in tabela.columns:
        tabela["cod_ibge"] = tabela["cod_ibge"].astype(str)
    return tabela


def _ler_csv_docs(caminho: Path, **kwargs) -> pd.DataFrame:
    if not caminho.exists():
        raise DadosIndisponiveis(
            f"Arquivo não encontrado: docs/potencial/{caminho.name}."
        )
    return pd.read_csv(caminho, **kwargs)


def carregar_base(
    pasta: Path = PASTA_PROCESSED, pasta_docs: Path = PASTA_DOCS_POTENCIAL
) -> BasePotencial:
    """Lê as Gold das Tarefas 2, 3, 4 e 6. DadosIndisponiveis se faltar arquivo."""
    tabelas = {
        nome: _ler_parquet(pasta / arquivo) for nome, arquivo in ARQUIVOS.items()
    }
    return BasePotencial(
        **tabelas,
        correlacao=_ler_csv_docs(pasta_docs / ARQUIVO_CORRELACAO, index_col=0),
        robustez=_ler_csv_docs(pasta_docs / ARQUIVO_ROBUSTEZ),
    )


# ═══════════════════ Recortes ═══════════════════


def validar_uf(base: BasePotencial, uf: str | None) -> str | None:
    if uf is None:
        return None
    sigla = uf.upper()
    if sigla not in set(base.municipal["uf"]):
        raise RecorteInexistente(f"UF '{uf}' não encontrada. Use uma das 27 siglas.")
    return sigla


def linha_municipio(base: BasePotencial, cod_ibge: str) -> pd.Series:
    linha = base.municipal[base.municipal["cod_ibge"] == str(cod_ibge)]
    if linha.empty:
        raise RecorteInexistente(
            f"Município '{cod_ibge}' não encontrado. Use o código IBGE de 7 dígitos."
        )
    return linha.iloc[0]


def municipios_da_uf(base: BasePotencial, uf: str) -> pd.DataFrame:
    """Lista (cod_ibge, nome) da UF, em ordem alfabética, para o filtro."""
    uf = validar_uf(base, uf)
    return (
        base.municipal.loc[base.municipal["uf"] == uf, ["cod_ibge", "nome"]]
        .sort_values("nome")
        .reset_index(drop=True)
    )


def _com_visao(tabela: pd.DataFrame, visao: str) -> pd.DataFrame:
    """Acrescenta y_visao, gap_visao e taxa_visao, padronizados para a visão."""
    colunas = COLUNAS_VISAO[visao]
    y = tabela[colunas["y"]].astype(float)
    return tabela.assign(
        y_visao=y,
        gap_visao=tabela["x_mwh_ano"] - y,
        taxa_visao=tabela[colunas["taxa"]].astype(float),
    )


def _totais(tabela: pd.DataFrame) -> dict[str, float]:
    x = float(tabela["x_mwh_ano"].sum())
    y = float(tabela["y_visao"].sum())
    return {
        "x_mwh_ano": x,
        "y_mwh_ano": y,
        "gap_mwh_ano": x - y,
        "taxa_realizacao": y / x if x else float("nan"),
    }


def _irradiacao_ponderada(tabela: pd.DataFrame) -> float:
    """H médio ponderado pelo kWp potencial (o peso de cada município em x)."""
    peso = tabela["kwp_potencial"].to_numpy(dtype=float)
    return float(np.average(tabela["irradiacao_kwh_m2_dia"], weights=peso))


def resumo_recorte(
    base: BasePotencial,
    visao: str = VISAO_PADRAO,
    uf: str | None = None,
    cod_ibge: str | None = None,
) -> dict:
    """Cards da página: x, y, gap e % realizado do Brasil, de uma UF ou município."""
    visao = normalizar_visao(visao)
    if cod_ibge is not None:
        linha = linha_municipio(base, cod_ibge)
        tabela = base.municipal[base.municipal["cod_ibge"] == linha["cod_ibge"]]
        nivel, nome = "municipio", f"{linha['nome']} ({linha['uf']})"
    elif uf is not None:
        uf = validar_uf(base, uf)
        tabela = base.municipal[base.municipal["uf"] == uf]
        nivel, nome = "uf", uf
    else:
        tabela, nivel, nome = base.municipal, "brasil", "Brasil"
    tabela = _com_visao(tabela, visao)
    return {
        "nivel": nivel,
        "nome": nome,
        "visao": visao,
        "n_municipios": len(tabela),
        "domicilios": int(tabela["domicilios"].sum()),
        "irradiacao_kwh_m2_dia": _irradiacao_ponderada(tabela),
        **_totais(tabela),
        "n_municipios_taxa_acima_1": int((tabela["taxa_visao"] > 1).sum()),
    }


def tabela_uf(base: BasePotencial, visao: str = VISAO_PADRAO, n_fatores: int = 3):
    """UFs x (H, x, y, gap, taxa) na visão, com os principais fatores do SHAP.

    A taxa é Σy / Σx (a mesma da Gold de UF); os fatores são os de maior
    contribuição absoluta na média ponderada da UF (ver explicar).
    """
    visao = normalizar_visao(visao)
    tabela = _com_visao(base.municipal, visao)
    linhas = []
    for uf, grupo in tabela.groupby("uf"):
        explicacao = explicar(base, visao, uf=uf)
        linhas.append(
            {
                "uf": uf,
                "regiao": grupo["regiao"].iloc[0],
                "n_municipios": len(grupo),
                "domicilios": int(grupo["domicilios"].sum()),
                "irradiacao_kwh_m2_dia": _irradiacao_ponderada(grupo),
                **_totais(grupo),
                "n_municipios_taxa_acima_1": int((grupo["taxa_visao"] > 1).sum()),
                "principais_fatores": [
                    f"{g['rotulo']} ({_pp(g['contribuicao_pp'])})"
                    for g in explicacao["grupos"][:n_fatores]
                ],
            }
        )
    return pd.DataFrame(linhas).sort_values("uf").reset_index(drop=True)


def taxa_municipios(base: BasePotencial, uf: str, visao: str = VISAO_PADRAO):
    """Taxa de realização dos municípios de uma UF (mapa municipal)."""
    visao = normalizar_visao(visao)
    uf = validar_uf(base, uf)
    tabela = _com_visao(base.municipal[base.municipal["uf"] == uf], visao)
    return tabela[
        ["cod_ibge", "nome", "uf", "x_mwh_ano", "y_visao", "gap_visao", "taxa_visao"]
    ].rename(
        columns={
            "y_visao": "y_mwh_ano",
            "gap_visao": "gap_mwh_ano",
            "taxa_visao": "taxa_realizacao",
        }
    )


# ═══════════════════ Explicação (SHAP) ═══════════════════


def _texto_valor(fator: Fator, valor: float) -> str:
    if valor is None or pd.isna(valor):
        return "sem dado"
    if fator.booleano:
        return "sim" if valor >= 0.5 else "não"
    numero = (
        f"{valor:,.{fator.casas}f}".replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )
    return fator.formato.format(numero)


def _texto_valor_agregado(fator: Fator, valor: float) -> str:
    """Na UF ou no Brasil, o booleano vira a fração (ponderada) de municípios."""
    if fator.booleano and valor is not None and not pd.isna(valor):
        return f"{valor * 100:.0f}% dos domicílios".replace(".", ",")
    return _texto_valor(fator, valor)


def _media_ponderada(tabela: pd.DataFrame, colunas, peso: pd.Series) -> pd.Series:
    w = peso.to_numpy(dtype=float)
    return pd.Series(
        {c: np.average(tabela[c].astype(float).to_numpy(), weights=w) for c in colunas}
    )


def explicar(
    base: BasePotencial,
    visao: str = VISAO_PADRAO,
    uf: str | None = None,
    cod_ibge: str | None = None,
) -> dict:
    """Contribuições SHAP do recorte, do maior para o menor efeito absoluto.

    Município: as contribuições do próprio município. UF e Brasil: média
    ponderada por domicílios dos municípios usados no treino, o mesmo método
    de shap_uf.parquet. Contribuição em pontos percentuais (p.p.) da taxa de
    realização prevista, em relação à média do modelo (valor_base).
    """
    visao = normalizar_visao(visao)
    shap = base.shap.merge(
        base.municipal[["cod_ibge", "uf", "nome", "domicilios"]], on="cod_ibge"
    ).merge(
        base.fatores[["cod_ibge", *{f.coluna_valor for f in FATORES.values()}]],
        on="cod_ibge",
        how="left",
    )
    colunas_valor = sorted({f.coluna_valor for f in FATORES.values()})
    if cod_ibge is not None:
        municipio = linha_municipio(base, cod_ibge)
        linha = shap[shap["cod_ibge"] == municipio["cod_ibge"]].iloc[0]
        nivel, nome = "municipio", f"{municipio['nome']} ({municipio['uf']})"
        valores = linha
        resumo = resumo_recorte(base, visao, cod_ibge=municipio["cod_ibge"])
        usado_no_treino = bool(linha["usado_no_treino"])
        texto_valor = _texto_valor
    else:
        uf = validar_uf(base, uf)
        recorte = shap[shap["usado_no_treino"].astype(bool)]
        if uf is not None:
            recorte = recorte[recorte["uf"] == uf]
        nivel, nome = ("uf", uf) if uf else ("brasil", "Brasil")
        peso = recorte["domicilios"]
        colunas = ["valor_base", "previsao", "alvo_observado", *COLUNAS_SHAP]
        linha = _media_ponderada(recorte, colunas, peso)
        valores = _media_ponderada(
            recorte.assign(**{c: recorte[c].astype(float) for c in colunas_valor}),
            colunas_valor,
            peso,
        )
        resumo = resumo_recorte(base, visao, uf=uf)
        usado_no_treino = True
        texto_valor = _texto_valor_agregado

    fatores = []
    for chave, fator in FATORES.items():
        contribuicao = float(linha[f"shap_{chave}"])
        valor = valores[fator.coluna_valor]
        valor = None if pd.isna(valor) else float(valor)
        efeito = "eleva" if contribuicao >= 0 else "reduz"
        valor_texto = texto_valor(fator, valor)
        pp = f"{abs(contribuicao) * 100:.1f}".replace(".", ",")
        fatores.append(
            {
                "fator": chave,
                "grupo": GRUPO_DO_FATOR[chave],
                "rotulo": fator.rotulo,
                "rotulo_no_grupo": rotulo_no_grupo(chave),
                "valor": valor,
                "valor_texto": valor_texto,
                "contribuicao": contribuicao,
                "contribuicao_pp": contribuicao * 100,
                "efeito": efeito,
                "frase": (
                    f"{fator.rotulo}, {valor_texto}: {efeito} a taxa prevista "
                    f"em {pp} p.p."
                ),
            }
        )
    fatores.sort(key=lambda f: abs(f["contribuicao"]), reverse=True)

    grupos = agrupar(fatores)
    valor_base = float(linha["valor_base"])
    previsao = float(linha["previsao"])
    taxa = resumo["taxa_realizacao"]
    diferenca_pp = (taxa - previsao) * 100
    para_baixo = _destaques(grupos, "reduz")
    para_cima = _destaques(grupos, "eleva")
    comparacao = (
        f"{nome} realiza {_pct(taxa)} {NA_VISAO[visao]}; pelo perfil, o modelo "
        f"esperaria {_pct(previsao)}. {_frase_esperado(diferenca_pp)}"
    )
    leitura = " ".join(
        [
            comparacao,
            _frase_sinal(
                para_baixo,
                "O que mais puxa a taxa para baixo (aumenta o gap)",
                "para baixo",
            ),
            _frase_sinal(
                para_cima, "O que mais puxa a taxa para cima (reduz o gap)", "para cima"
            ),
        ]
    )
    aviso = (
        None
        if visao == "corrigida"
        else (
            "As contribuições SHAP vêm do modelo treinado na visão corrigida, o único "
            f"com explicação por município. A taxa observada é calculada {NA_VISAO[visao]}; "
            "o ranking global de fatores do modelo ajustado a esta visão está em "
            "ranking_global_visao."
        )
    )
    return {
        "nivel": nivel,
        "nome": nome,
        "cod_ibge": None if cod_ibge is None else str(cod_ibge),
        "visao": visao,
        "visao_modelo": "corrigida",
        "taxa_observada": taxa,
        "taxa_prevista": previsao,
        "valor_base": valor_base,
        "usado_no_treino": usado_no_treino,
        "diferenca_pp": diferenca_pp,
        "comparacao_esperado": comparacao,
        "leitura": leitura,
        "aviso_visao": aviso,
        "puxam_para_baixo": [g["rotulo"] for g in para_baixo],
        "puxam_para_cima": [g["rotulo"] for g in para_cima],
        "grupos": grupos,
        "fatores": fatores,
        "ranking_global_visao": ranking_global(base, visao),
    }


def agrupar(fatores: list[dict]) -> list[dict]:
    """Soma as contribuições SHAP por família (SHAP é aditivo), do maior para
    o menor efeito absoluto."""
    somas: dict[str, float] = {}
    membros: dict[str, list[str]] = {}
    for fator in fatores:
        grupo = fator["grupo"]
        somas[grupo] = somas.get(grupo, 0.0) + fator["contribuicao"]
        membros.setdefault(grupo, []).append(fator["fator"])
    grupos = [
        {
            "grupo": grupo,
            "rotulo": rotulo_grupo(grupo),
            "fatores": membros[grupo],
            "contribuicao": soma,
            "contribuicao_pp": soma * 100,
            "efeito": "eleva" if soma >= 0 else "reduz",
        }
        for grupo, soma in somas.items()
    ]
    return sorted(grupos, key=lambda g: abs(g["contribuicao"]), reverse=True)


def _destaques(grupos: list[dict], efeito: str) -> list[dict]:
    """Até N_GRUPOS_LEITURA grupos do sinal pedido, com |efeito| >= LIMIAR_LEITURA_PP."""
    return [
        g
        for g in grupos
        if g["efeito"] == efeito and abs(g["contribuicao_pp"]) >= LIMIAR_LEITURA_PP
    ][:N_GRUPOS_LEITURA]


def _pp(valor_pp: float) -> str:
    sinal = "+" if valor_pp >= 0 else "−"
    return f"{sinal}{abs(valor_pp):.1f} p.p.".replace(".", ",", 1)


def _minuscula(rotulo: str) -> str:
    """'Renda' -> 'renda'; siglas no início (ex.: 'ICMS') ficam como estão."""
    if len(rotulo) > 1 and rotulo[1].isupper():
        return rotulo
    return rotulo[0].lower() + rotulo[1:]


def _lista(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else f"{', '.join(itens[:-1])} e {itens[-1]}"


def _frase_sinal(grupos: list[dict], abertura: str, direcao: str) -> str:
    if not grupos:
        limiar = f"{LIMIAR_LEITURA_PP:.0f}"
        return f"Nenhum fator medido puxa a taxa {direcao} mais de {limiar} p.p."
    partes = [
        f"{_minuscula(g['rotulo'])} ({_pp(g['contribuicao_pp'])})" for g in grupos
    ]
    return f"{abertura}: {_lista(partes)}."


def _frase_esperado(diferenca_pp: float) -> str:
    distancia = f"{abs(diferenca_pp):.1f}".replace(".", ",")
    if diferenca_pp <= -TOLERANCIA_ESPERADO_PP:
        return (
            f"Abaixo do esperado em {distancia} p.p.: há espaço que os fatores "
            "medidos não explicam."
        )
    if diferenca_pp >= TOLERANCIA_ESPERADO_PP:
        return (
            f"Acima do esperado em {distancia} p.p.: aproveita mais do que o perfil "
            "sugere."
        )
    return "Em linha com o esperado pelo perfil."


def ranking_global(base: BasePotencial, visao: str, n: int = 5) -> list[str]:
    """Fatores mais importantes no modelo ajustado à visão (robustez, Tarefa 4)."""
    visao = normalizar_visao(visao)
    tabela = base.robustez[base.robustez["visao"] == visao].sort_values("rank")
    return [FATORES[f].rotulo if f in FATORES else f for f in tabela["fator"].head(n)]


def _pct(valor: float) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    return f"{valor * 100:.1f}%".replace(".", ",")


def matriz_correlacao(base: BasePotencial) -> pd.DataFrame:
    """Matriz de Spearman da Tarefa 4 com rótulos legíveis."""
    rotulos = {chave: f.rotulo for chave, f in FATORES.items()}
    rotulos.update(
        {
            "alvo": "Taxa de realização",
            "icms_ano_inicio_isencao": "Ano de início da isenção de ICMS",
            "area_km2": "Área do município",
        }
    )
    return base.correlacao.rename(index=rotulos, columns=rotulos)


# ═══════════════════ Cenários 2030–2050 ═══════════════════


def _projetar_visao(
    tabela: pd.DataFrame, y_visao: pd.Series, visao: str
) -> pd.DataFrame:
    """y e gap projetados da visão, com mediana e faixa (mín.–máx.)."""
    prefixo = Y_PROJETADO_GOLD[visao]
    saida = pd.DataFrame(index=tabela.index)
    for sufixo in ("", "_min", "_max"):
        coluna_gold = f"{prefixo}_projetado{sufixo}_mwh_ano" if prefixo else None
        if coluna_gold and coluna_gold in tabela.columns:
            saida[f"y{sufixo}"] = tabela[coluna_gold]
        else:  # razão da visão corrigida (ver docstring do módulo)
            razao = tabela[f"y_projetado{sufixo}_mwh_ano"] / tabela["y_mwh_ano"]
            saida[f"y{sufixo}"] = y_visao * razao.where(tabela["y_mwh_ano"] > 0, 1.0)
    saida["gap"] = tabela["x_projetado_mwh_ano"] - saida["y"]
    candidatos = np.column_stack(
        [
            tabela["x_projetado_min_mwh_ano"] - saida["y_min"],
            tabela["x_projetado_max_mwh_ano"] - saida["y_max"],
        ]
    )
    saida["gap_min"] = candidatos.min(axis=1)
    saida["gap_max"] = candidatos.max(axis=1)
    # Na Gold, a faixa do gap é calculada modelo a modelo: prevalece quando existe.
    prefixo_gap = GAP_PROJETADO_GOLD[visao]
    for sufixo in ("", "_min", "_max"):
        coluna_gold = (
            f"{prefixo_gap}_projetado{sufixo}_mwh_ano" if prefixo_gap else None
        )
        if coluna_gold and coluna_gold in tabela.columns:
            saida[f"gap{sufixo}"] = tabela[coluna_gold]
    return saida


def _tabela_cenarios(projecao: pd.DataFrame, y_atual: pd.Series, visao: str):
    proj = _projetar_visao(projecao, y_atual, visao)
    x = projecao["x_mwh_ano"]
    return pd.DataFrame(
        {
            "cenario": projecao["cenario"],
            "rotulo_cenario": projecao["cenario"].map(CENARIOS),
            "janela": projecao["janela"],
            "delta_mediano": projecao["delta_mediano"],
            "delta_min": projecao["delta_min"],
            "delta_max": projecao["delta_max"],
            "irradiacao_observada": projecao["H_observada"],
            "irradiacao_projetada": projecao["H_projetada"],
            "irradiacao_projetada_min": projecao["H_projetada_min"],
            "irradiacao_projetada_max": projecao["H_projetada_max"],
            "x_atual_mwh_ano": x,
            "x_projetado_mwh_ano": projecao["x_projetado_mwh_ano"],
            "x_projetado_min_mwh_ano": projecao["x_projetado_min_mwh_ano"],
            "x_projetado_max_mwh_ano": projecao["x_projetado_max_mwh_ano"],
            "y_atual_mwh_ano": y_atual,
            "y_projetado_mwh_ano": proj["y"],
            "y_projetado_min_mwh_ano": proj["y_min"],
            "y_projetado_max_mwh_ano": proj["y_max"],
            "gap_atual_mwh_ano": x - y_atual,
            "gap_projetado_mwh_ano": proj["gap"],
            "gap_projetado_min_mwh_ano": proj["gap_min"],
            "gap_projetado_max_mwh_ano": proj["gap_max"],
            "taxa_realizacao": y_atual / x,
            "taxa_projetada": proj["y"] / projecao["x_projetado_mwh_ano"],
            "n_modelos": projecao["n_modelos"],
        }
    )


def cenarios_municipio(
    base: BasePotencial, cod_ibge: str, visao: str = VISAO_PADRAO
) -> pd.DataFrame:
    """Projeção 2030–2050 de um município: 2 cenários x 2 janelas."""
    visao = normalizar_visao(visao)
    municipio = linha_municipio(base, cod_ibge)
    projecao = base.projecao_municipal[
        base.projecao_municipal["cod_ibge"] == municipio["cod_ibge"]
    ].reset_index(drop=True)
    if projecao.empty:
        raise RecorteInexistente(f"Município '{cod_ibge}' sem projeção na Gold.")
    y_atual = pd.Series(
        float(municipio[COLUNAS_VISAO[visao]["y"]]), index=projecao.index
    )
    tabela = _tabela_cenarios(projecao, y_atual, visao)
    tabela = tabela.sort_values(["cenario", "janela"]).reset_index(drop=True)
    distancia = float(projecao["distancia_celula_km"].iloc[0])
    tabela["distancia_celula_km"] = distancia
    return tabela


def cenarios_uf(
    base: BasePotencial, visao: str = VISAO_PADRAO, uf: str | None = None
) -> pd.DataFrame:
    """Projeção 2030–2050 por UF (todas, ou uma)."""
    visao = normalizar_visao(visao)
    uf = validar_uf(base, uf)
    projecao = base.projecao_uf
    if uf is not None:
        projecao = projecao[projecao["uf"] == uf]
    projecao = projecao.reset_index(drop=True)
    y_uf = base.uf.set_index("uf")[COLUNAS_VISAO[visao]["y"]]
    y_atual = projecao["uf"].map(y_uf).astype(float)
    tabela = _tabela_cenarios(projecao, y_atual, visao)
    tabela.insert(0, "uf", projecao["uf"])  # mesmo índice: alinhado por linha
    return tabela.sort_values(["cenario", "janela", "uf"]).reset_index(drop=True)


def cenarios_municipios_uf(
    base: BasePotencial, uf: str, cenario: str, janela: str
) -> pd.DataFrame:
    """Delta mediano e faixa dos municípios de uma UF (mapa dos cenários)."""
    uf = validar_uf(base, uf)
    projecao = base.projecao_municipal
    filtro = (
        (projecao["uf"] == uf)
        & (projecao["cenario"] == cenario)
        & (projecao["janela"] == janela)
    )
    return projecao.loc[
        filtro, ["cod_ibge", "delta_mediano", "delta_min", "delta_max"]
    ].merge(base.municipal[["cod_ibge", "nome"]], on="cod_ibge")


# ═══════════════════ Malhas do mapa ═══════════════════


def caminho_malha(uf: str | None = None, pasta: Path = PASTA_MALHAS) -> Path:
    """GeoJSON simplificado das UFs (uf=None) ou dos municípios de uma UF."""
    caminho = (
        pasta / "uf.geojson" if uf is None else pasta / "municipios" / f"{uf}.geojson"
    )
    if not caminho.exists():
        raise DadosIndisponiveis(
            f"Malha do mapa não encontrada: {caminho.name}. "
            "Rode python -m src.potencial.malha_mapa."
        )
    return caminho
