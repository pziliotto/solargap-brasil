"""
PROJETO: SolarGap Brasil
ARQUIVO: carregamento.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/09/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Carga da camada Gold e cálculos usados pelo dashboard. Todas as funções
    públicas usam @st.cache_data: a leitura dos CSVs e os cálculos pesados
    (agregações filtradas, contagem de termos, nuvem de palavras) acontecem
    uma vez por combinação de parâmetros, e não a cada interação do usuário.

OBS.:
    Os indicadores per capita são recalculados aqui, depois dos filtros, e
    não lidos prontos da gold_uf.csv — por isso a Gold guarda o menor grão.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from wordcloud import WordCloud

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PASTA_PROCESSED = PROJECT_ROOT / "data" / "processed"
SEPARADOR = ";"

# Palavras sem valor informativo para a nuvem: artigos, preposições,
# pronomes, verbos auxiliares e jargão de texto jornalístico.
STOPWORDS = set(
    [
        "a",
        "ao",
        "aos",
        "aquela",
        "aquelas",
        "aquele",
        "aqueles",
        "aquilo",
        "as",
        "até",
        "com",
        "como",
        "da",
        "das",
        "de",
        "dela",
        "delas",
        "dele",
        "deles",
        "depois",
        "do",
        "dos",
        "e",
        "ela",
        "elas",
        "ele",
        "eles",
        "em",
        "entre",
        "era",
        "eram",
        "essa",
        "essas",
        "esse",
        "esses",
        "esta",
        "estas",
        "este",
        "estes",
        "eu",
        "foi",
        "foram",
        "há",
        "isso",
        "isto",
        "já",
        "lhe",
        "lhes",
        "mais",
        "mas",
        "me",
        "mesmo",
        "meu",
        "minha",
        "muito",
        "na",
        "nas",
        "nem",
        "no",
        "nos",
        "nós",
        "num",
        "numa",
        "o",
        "os",
        "ou",
        "para",
        "pela",
        "pelas",
        "pelo",
        "pelos",
        "por",
        "qual",
        "quando",
        "que",
        "quem",
        "se",
        "sem",
        "ser",
        "seu",
        "seus",
        "só",
        "sua",
        "suas",
        "também",
        "te",
        "tem",
        "têm",
        "ter",
        "um",
        "uma",
        "umas",
        "uns",
        "você",
        "vocês",
        "à",
        "às",
        "é",
        "são",
        "está",
        "estão",
        "estava",
        "será",
        "serão",
        "seria",
        "pode",
        "podem",
        "poderá",
        "deve",
        "devem",
        "vai",
        "vão",
        "sobre",
        "após",
        "ainda",
        "segundo",
        "disse",
        "afirmou",
        "explicou",
        "destacou",
        "informou",
        "acordo",
        "ano",
        "anos",
        "mil",
        "milhão",
        "milhões",
        "bilhão",
        "bilhões",
        "cerca",
        "além",
        "outros",
        "outras",
        "outro",
        "outra",
        "cada",
        "todo",
        "toda",
        "todos",
        "todas",
        "onde",
        "assim",
        "então",
        "porque",
        "porém",
        "bem",
        "apenas",
        "agência",
        "brasil",
        "hoje",
        "dia",
        "dias",
        "mês",
        "meses",
        "parte",
        "forma",
        "desde",
        "contra",
        "durante",
        "sendo",
        "tendo",
        "feito",
        "fazer",
        "faz",
        "vez",
        "vezes",
        "grande",
        "grandes",
        "novo",
        "nova",
        "novos",
        "novas",
        "primeiro",
        "primeira",
        "maior",
        "maiores",
        "menor",
        "menores",
        "ser",
        "sido",
        "estar",
        "tinha",
        "tinham",
        "caso",
        "casos",
        "sobre",
        "total",
        "através",
        "conforme",
        "enquanto",
        "dessa",
        "desse",
        "desta",
        "deste",
        "nessa",
        "nesse",
        "nesta",
        "neste",
        "pois",
        "lá",
        "aqui",
        "aí",
        "tanto",
        "tanta",
        "tão",
        "quanto",
        "quanta",
    ]
)
PADRAO_TOKEN = re.compile(r"[a-záàâãéêíóôõúüç]+")
TAMANHO_MINIMO_TOKEN = 3


# ═══════════════════ Carga ═══════════════════


@st.cache_data(show_spinner="Carregando dados...")
def carregar_agregado() -> pd.DataFrame:
    return pd.read_csv(PASTA_PROCESSED / "gold_mmgd_agregado.csv", sep=SEPARADOR)


@st.cache_data(show_spinner=False)
def carregar_uf() -> pd.DataFrame:
    return pd.read_csv(PASTA_PROCESSED / "gold_uf.csv", sep=SEPARADOR)


@st.cache_data(show_spinner=False)
def carregar_corpus() -> pd.DataFrame:
    corpus = pd.read_csv(
        PASTA_PROCESSED / "corpus_noticias.csv",
        sep=SEPARADOR,
        parse_dates=["data_publicacao", "coletado_em"],
    )
    corpus["ufs_mencionadas"] = corpus["ufs_mencionadas"].fillna("")
    return corpus


# ═══════════════════ Indicadores ═══════════════════


def _filtrar(
    agregado: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
    classes: tuple[str, ...],
    incluir_imputados: bool,
) -> pd.DataFrame:
    filtro = agregado["ano"].between(ano_inicio, ano_fim) & agregado[
        "classe_consumo"
    ].isin(classes)
    if not incluir_imputados:
        filtro &= ~agregado["fonte_imputada"]
    return agregado[filtro]


@st.cache_data(show_spinner=False)
def indicadores_por_uf(
    agregado: pd.DataFrame,
    dim_uf: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
    classes: tuple[str, ...],
    incluir_imputados: bool,
) -> pd.DataFrame:
    """Soma o agregado filtrado por UF e recalcula os indicadores per capita."""
    filtrado = _filtrar(agregado, ano_inicio, ano_fim, classes, incluir_imputados)
    filtrado = filtrado.assign(
        qtd_imputados=filtrado["qtd_empreendimentos"].where(
            filtrado["fonte_imputada"], 0
        )
    )
    totais = filtrado.groupby("sigla_uf", as_index=False).agg(
        potencia_kw=("potencia_kw", "sum"),
        qtd_empreendimentos=("qtd_empreendimentos", "sum"),
        qtd_imputados=("qtd_imputados", "sum"),
    )

    base = dim_uf[["sigla_uf", "nome_uf", "regiao", "populacao"]].merge(
        totais, on="sigla_uf", how="left"
    )
    base[["potencia_kw", "qtd_empreendimentos", "qtd_imputados"]] = base[
        ["potencia_kw", "qtd_empreendimentos", "qtd_imputados"]
    ].fillna(0)

    base["potencia_mw"] = base["potencia_kw"] / 1_000
    base["watts_por_habitante"] = base["potencia_kw"] * 1_000 / base["populacao"]
    base["empreendimentos_por_100k_hab"] = (
        base["qtd_empreendimentos"] / base["populacao"] * 100_000
    )
    return base


@st.cache_data(show_spinner=False)
def serie_anual(
    agregado: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
    classes: tuple[str, ...],
    incluir_imputados: bool,
) -> pd.DataFrame:
    """Potência (MW) e empreendimentos por UF e ano, já filtrados."""
    filtrado = _filtrar(agregado, ano_inicio, ano_fim, classes, incluir_imputados)
    serie = filtrado.groupby(["sigla_uf", "ano"], as_index=False).agg(
        potencia_kw=("potencia_kw", "sum"),
        qtd_empreendimentos=("qtd_empreendimentos", "sum"),
    )
    serie["potencia_mw"] = serie["potencia_kw"] / 1_000
    return serie


# ═══════════════════ Texto ═══════════════════


@st.cache_data(show_spinner=False)
def frequencia_termos(textos: tuple[str, ...]) -> dict[str, int]:
    """Conta os termos do corpus, sem stopwords, números e palavras curtas."""
    contagem: Counter = Counter()
    for texto in textos:
        for token in PADRAO_TOKEN.findall(str(texto).lower()):
            if len(token) >= TAMANHO_MINIMO_TOKEN and token not in STOPWORDS:
                contagem[token] += 1
    return dict(contagem)


@st.cache_data(show_spinner="Gerando nuvem de palavras...")
def gerar_nuvem(frequencias: dict[str, int]) -> np.ndarray:
    nuvem = WordCloud(
        width=1000,
        height=500,
        background_color="white",
        colormap="viridis",
        max_words=100,
        random_state=42,  # mesma nuvem a cada execução
    )
    return nuvem.generate_from_frequencies(frequencias).to_array()
