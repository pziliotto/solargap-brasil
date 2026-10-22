"""
PROJETO: SolarGap Brasil
ARQUIVO: carregamento.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/09/2026
ATUALIZAÇÃO: 21/10/2026 — TP3: regra de negócio movida para src/servicos;
             este módulo virou só a camada de cache do Streamlit

DESCRIÇÃO:
    Envolve as funções de src/servicos com @st.cache_data. A leitura dos CSVs
    e os cálculos pesados acontecem uma vez por combinação de parâmetros, e não
    a cada interação do usuário.

POR QUE A SEPARAÇÃO (TP3):
    A API (FastAPI) calcula os mesmos indicadores. Com a regra em src/servicos,
    painel e API usam o mesmo código; aqui fica só o que é específico do
    Streamlit: cache e geração da imagem da nuvem de palavras.

INVALIDAÇÃO:
    Quando o usuário envia uma notícia pela API (página API), o painel chama
    carregar_corpus.clear() para que a notícia apareça sem reiniciar o app.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
from wordcloud import WordCloud

from src.servicos import dados, indicadores, texto

# ═══════════════════ Carga ═══════════════════


@st.cache_data(show_spinner="Carregando dados...")
def carregar_agregado() -> pd.DataFrame:
    return dados.carregar_agregado()


@st.cache_data(show_spinner=False)
def carregar_uf() -> pd.DataFrame:
    return dados.carregar_uf()


@st.cache_data(show_spinner=False)
def carregar_icms() -> pd.DataFrame | None:
    return dados.carregar_icms()


@st.cache_data(show_spinner=False)
def carregar_corpus() -> pd.DataFrame:
    """Corpus coletado + notícias enviadas pela API."""
    return dados.carregar_corpus_completo()


# ═══════════════════ Indicadores ═══════════════════


@st.cache_data(show_spinner=False)
def indicadores_por_uf(
    agregado: pd.DataFrame,
    dim_uf: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
    classes: tuple[str, ...],
    incluir_imputados: bool,
) -> pd.DataFrame:
    return indicadores.indicadores_por_uf(
        agregado, dim_uf, ano_inicio, ano_fim, classes, incluir_imputados
    )


@st.cache_data(show_spinner=False)
def serie_anual(
    agregado: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
    classes: tuple[str, ...],
    incluir_imputados: bool,
) -> pd.DataFrame:
    return indicadores.serie_anual(
        agregado, ano_inicio, ano_fim, classes, incluir_imputados
    )


@st.cache_data(show_spinner=False)
def serie_acumulada(
    agregado: pd.DataFrame, classes: tuple[str, ...], incluir_imputados: bool
) -> pd.DataFrame:
    return indicadores.serie_acumulada(agregado, classes, incluir_imputados)


@st.cache_data(show_spinner=False)
def taxa_crescimento(
    agregado: pd.DataFrame,
    classes: tuple[str, ...],
    incluir_imputados: bool,
    ano_base: int,
    ano_final: int,
) -> tuple[pd.DataFrame, float]:
    return indicadores.taxa_crescimento(
        agregado, classes, incluir_imputados, ano_base, ano_final
    )


# ═══════════════════ Texto ═══════════════════


@st.cache_data(show_spinner=False)
def frequencia_termos(textos: tuple[str, ...]) -> dict[str, int]:
    return texto.frequencia_termos(textos)


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
