"""
PROJETO: SolarGap Brasil
ARQUIVO: carregamento.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/09/2026
ATUALIZAÇÃO: 21/10/2026 — TP3: regra de negócio movida para src/servicos;
             este módulo virou só a camada de cache do Streamlit
             22/11/2026 — TP4.5, Tarefa 7: potencial solar e malhas do mapa

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

import json

import numpy as np
import pandas as pd
import streamlit as st
from wordcloud import WordCloud

from src.servicos import dados, indicadores, potencial, texto

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
    visao: str,
) -> pd.DataFrame:
    return indicadores.indicadores_por_uf(
        agregado, dim_uf, ano_inicio, ano_fim, classes, visao
    )


@st.cache_data(show_spinner=False)
def serie_anual(
    agregado: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
    classes: tuple[str, ...],
    visao: str,
) -> pd.DataFrame:
    return indicadores.serie_anual(
        agregado, ano_inicio, ano_fim, classes, visao
    )


@st.cache_data(show_spinner=False)
def serie_acumulada(
    agregado: pd.DataFrame, classes: tuple[str, ...], visao: str
) -> pd.DataFrame:
    return indicadores.serie_acumulada(agregado, classes, visao)


@st.cache_data(show_spinner=False)
def taxa_crescimento(
    agregado: pd.DataFrame,
    classes: tuple[str, ...],
    visao: str,
    ano_base: int,
    ano_final: int,
) -> tuple[pd.DataFrame, float]:
    return indicadores.taxa_crescimento(
        agregado, classes, visao, ano_base, ano_final
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


# ═══════════════════ Potencial solar (TP4.5, Tarefa 7) ═══════════════════
# O serviço recebe a BasePotencial; o argumento com "_" não entra na chave do
# cache (a base é lida uma vez e não muda durante a sessão).


@st.cache_data(show_spinner="Carregando o potencial solar...")
def carregar_base_potencial() -> potencial.BasePotencial:
    return potencial.carregar_base()


@st.cache_data(show_spinner=False)
def resumo_potencial(
    _base: potencial.BasePotencial, visao: str, uf: str | None, cod_ibge: str | None
) -> dict:
    return potencial.resumo_recorte(_base, visao, uf=uf, cod_ibge=cod_ibge)


@st.cache_data(show_spinner=False)
def explicacao_potencial(
    _base: potencial.BasePotencial, visao: str, uf: str | None, cod_ibge: str | None
) -> dict:
    return potencial.explicar(_base, visao, uf=uf, cod_ibge=cod_ibge)


@st.cache_data(show_spinner="Calculando a tabela por UF...")
def tabela_potencial_uf(_base: potencial.BasePotencial, visao: str) -> pd.DataFrame:
    return potencial.tabela_uf(_base, visao)


@st.cache_data(show_spinner=False)
def taxa_municipios(_base: potencial.BasePotencial, uf: str, visao: str) -> pd.DataFrame:
    return potencial.taxa_municipios(_base, uf, visao)


@st.cache_data(show_spinner=False)
def cenarios_uf(
    _base: potencial.BasePotencial, visao: str, uf: str | None
) -> pd.DataFrame:
    return potencial.cenarios_uf(_base, visao, uf)


@st.cache_data(show_spinner=False)
def cenarios_municipio(
    _base: potencial.BasePotencial, cod_ibge: str, visao: str
) -> pd.DataFrame:
    return potencial.cenarios_municipio(_base, cod_ibge, visao)


@st.cache_data(show_spinner="Carregando o mapa...")
def malha(uf: str | None) -> dict:
    """GeoJSON simplificado (UFs ou municípios de uma UF)."""
    return json.loads(potencial.caminho_malha(uf).read_text(encoding="utf-8"))
