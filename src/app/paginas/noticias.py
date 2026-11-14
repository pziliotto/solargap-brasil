"""
PROJETO: SolarGap Brasil
ARQUIVO: paginas/noticias.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026 (origem: aba Notícias do demo_app.py, TP2)
ATUALIZAÇÃO:

DESCRIÇÃO:
    Estatísticas do corpus de notícias, agora com várias fontes (TP3):
    filtro por fonte e por UF, nuvem de palavras, termos frequentes, volume
    por ano e por fonte, UFs mais mencionadas e tabela com links.

NÍVEIS DE TEXTO:
    Notícias de nível "integral" contribuem com o texto completo para a nuvem;
    as de nível "metadados" (fontes sem autorização de cópia), só com título e
    linha fina. A mesma regra vale para a entrada do modelo no TP4.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from src.app import carregamento as dados
from src.app.componentes import SIGLAS, fmt, rodape
from src.preparacao import esquema
from src.servicos.noticias import TAG_ENVIO_API, filtrar_noticias, lista_ufs

corpus = dados.carregar_corpus()

st.title("📰 Notícias")
if corpus.empty:
    st.info(
        "O corpus está vazio. Rode `python -m src.data_acquisition.noticias` na raiz do projeto."
    )
    st.stop()

integral = corpus["nivel_texto"] == esquema.NIVEL_INTEGRAL
corpus = corpus.assign(
    conteudo=corpus["titulo"]
    + " "
    + corpus["linha_fina"]
    + corpus["texto"].where(integral, "").radd(" ")
)

fontes = sorted(corpus["fonte"].unique())
st.markdown(
    f"Corpus de **{len(corpus)} notícias** sobre energia solar e geração distribuída, de "
    f"{len(fontes)} fonte(s), coletadas por web scraping (BeautifulSoup)."
)

frequencias_gerais = dados.frequencia_termos(tuple(corpus["conteudo"]))
termos_frequentes = sorted(
    frequencias_gerais, key=frequencias_gerais.get, reverse=True
)[:40]

c1, c2, c3 = st.columns(3)
fontes_escolhidas = c1.multiselect(
    "Fontes", fontes, default=fontes, key="fontes_noticias"
)
uf_noticia = c2.selectbox(
    "Notícias que mencionam", ["Todas as UFs"] + SIGLAS, key="uf_noticia"
)
ocultar = c3.multiselect(
    "Ocultar termos da nuvem",
    sorted(set(termos_frequentes) | {"energia", "solar"}),
    default=["energia", "solar"],
    key="termos_ocultos",
    help="Os termos do próprio tema dominam a nuvem e escondem o resto.",
)

selecao = corpus[corpus["fonte"].isin(fontes_escolhidas)]
if uf_noticia != "Todas as UFs":
    selecao = filtrar_noticias(selecao, uf=uf_noticia)

if selecao.empty:
    st.info("Nenhuma notícia para os filtros escolhidos.")
    st.stop()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Notícias", len(selecao))
k2.metric("Fontes", selecao["fonte"].nunique())
datas = selecao["data_publicacao"].dropna()
k3.metric("Período", f"{datas.min():%Y} – {datas.max():%Y}" if not datas.empty else "—")
k4.metric(
    "Com texto integral",
    f"{fmt((selecao['nivel_texto'] == esquema.NIVEL_INTEGRAL).mean() * 100)}%",
)

frequencias = dados.frequencia_termos(tuple(selecao["conteudo"]))
frequencias = {t: n for t, n in frequencias.items() if t not in ocultar}
mais_frequentes = dict(
    sorted(frequencias.items(), key=lambda item: item[1], reverse=True)[:150]
)

col_nuvem, col_termos = st.columns([3, 2])
with col_nuvem:
    st.subheader("Nuvem de palavras")
    if mais_frequentes:
        st.image(dados.gerar_nuvem(mais_frequentes), width="stretch")
with col_termos:
    st.subheader("Termos mais frequentes")
    top = pd.DataFrame(
        list(mais_frequentes.items())[:15], columns=["termo", "ocorrências"]
    )
    figura = px.bar(top.iloc[::-1], x="ocorrências", y="termo", orientation="h")
    figura.update_layout(height=420, yaxis_title=None, margin=dict(t=10, b=10))
    st.plotly_chart(figura, width="stretch")

col_ano, col_uf = st.columns(2)
with col_ano:
    st.subheader("Notícias por ano e fonte")
    por_ano = (
        selecao.dropna(subset=["data_publicacao"])
        .assign(ano=lambda d: d["data_publicacao"].dt.year)
        .groupby(["ano", "fonte"], as_index=False)
        .size()
    )
    figura = px.bar(
        por_ano,
        x="ano",
        y="size",
        color="fonte",
        labels={"ano": "Ano", "size": "Notícias", "fonte": "Fonte"},
    )
    figura.update_layout(
        height=340, margin=dict(t=10, b=10), xaxis=dict(dtick=1), legend_title=None
    )
    st.plotly_chart(figura, width="stretch")
with col_uf:
    st.subheader("UFs mais mencionadas")
    mencoes = (
        selecao["ufs_mencionadas"]
        .map(lista_ufs)
        .explode()
        .dropna()
        .value_counts()
        .head(10)
    )
    if mencoes.empty:
        st.caption("Nenhuma UF mencionada no recorte.")
    else:
        figura = px.bar(
            x=mencoes.values[::-1],
            y=mencoes.index[::-1],
            orientation="h",
            labels={"x": "Notícias", "y": "UF"},
        )
        figura.update_layout(height=340, margin=dict(t=10, b=10))
        st.plotly_chart(figura, width="stretch")
        st.caption(
            "Compare a atenção da imprensa com o ranking de adoção da página Panorama."
        )

st.subheader("Notícias")
st.dataframe(
    selecao[
        ["data_publicacao", "fonte", "titulo", "ufs_mencionadas", "nivel_texto", "url"]
    ],
    column_config={
        "data_publicacao": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "fonte": "Fonte",
        "titulo": st.column_config.TextColumn("Título", width="large"),
        "ufs_mencionadas": "UFs mencionadas",
        "nivel_texto": "Nível",
        "url": st.column_config.LinkColumn("Link", display_text="abrir"),
    },
    hide_index=True,
    width="stretch",
)

enviadas = int((corpus["tag_origem"] == TAG_ENVIO_API).sum())
st.caption(
    "Fontes: Agência Brasil e Agência Gov (EBC) — reprodução autorizada mediante indicação da "
    "fonte. Notícias de nível 'metadados' guardam só título, linha fina e link."
    + (f" Inclui {enviadas} notícia(s) enviada(s) pela API." if enviadas else "")
)
rodape()
