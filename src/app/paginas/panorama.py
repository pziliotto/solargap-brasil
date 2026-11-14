"""
PROJETO: SolarGap Brasil
ARQUIVO: paginas/panorama.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026 (origem: aba Panorama do demo_app.py, TP2)
ATUALIZAÇÃO:

DESCRIÇÃO:
    KPIs do recorte filtrado e ranking das 27 UFs na métrica escolhida, com a
    média nacional como referência e destaque opcional de uma UF.

FILTROS:
    Todos os da barra lateral. Os indicadores per capita são recalculados
    depois dos filtros, a partir do grão da Gold.
"""

import plotly.express as px
import streamlit as st

from src.app import carregamento as dados
from src.app.componentes import (
    COR_BASE,
    COR_DESTAQUE,
    aviso_imputados,
    filtros_atuais,
    fmt,
    rodape,
    uf_em_destaque,
)
from src.servicos import indicadores

filtros = filtros_atuais()
metrica = filtros.info_metrica
coluna = filtros.metrica

indicadores_uf = dados.indicadores_por_uf(
    dados.carregar_agregado(),
    dados.carregar_uf(),
    filtros.ano_inicio,
    filtros.ano_fim,
    filtros.classes,
    filtros.incluir_imputados,
)
referencia = indicadores.media_brasil(indicadores_uf)

st.title("📊 Panorama")
st.caption(
    f"Conexões de {filtros.ano_inicio} a {filtros.ano_fim} · visão: {filtros.visao}"
)
aviso_imputados(indicadores_uf, filtros.incluir_imputados)

lider = indicadores.ranking(indicadores_uf, coluna).iloc[0]
k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "Potência instalada", f"{fmt(indicadores_uf['potencia_kw'].sum() / 1_000, 1)} MW"
)
k2.metric("Empreendimentos", fmt(indicadores_uf["qtd_empreendimentos"].sum()))
k3.metric("Média Brasil", f"{fmt(referencia['watts_por_habitante'], 1)} W/hab")
k4.metric(f"Líder em {metrica.rotulo_frase}", lider["nome_uf"])

destaque = uf_em_destaque("Destacar uma UF no ranking")

ordenado = indicadores_uf.sort_values(coluna, ascending=True)
rotulos = {
    coluna: metrica.rotulo,
    "sigla_uf": "UF",
    "regiao": "Região",
    "nome_uf": "Estado",
}

if destaque == "Nenhuma":
    figura = px.bar(
        ordenado,
        x=coluna,
        y="sigla_uf",
        orientation="h",
        color="regiao",
        hover_data={"nome_uf": True, "regiao": True},
        labels=rotulos,
    )
else:
    figura = px.bar(
        ordenado,
        x=coluna,
        y="sigla_uf",
        orientation="h",
        hover_data={"nome_uf": True, "regiao": True},
        labels=rotulos,
    )
    figura.update_traces(
        marker_color=[
            COR_DESTAQUE if sigla == destaque else COR_BASE
            for sigla in ordenado["sigla_uf"]
        ]
    )

if metrica.per_capita:
    figura.add_vline(
        x=referencia[coluna],
        line_dash="dash",
        line_color="gray",
        annotation_text="Média Brasil",
        annotation_position="top",
    )

figura.update_layout(
    height=720, yaxis_title=None, margin=dict(t=40, b=10), legend_title=None
)
st.plotly_chart(figura, width="stretch")

if destaque != "Nenhuma":
    posicao = indicadores.posicoes(indicadores_uf, destaque)[coluna]
    linha = indicadores_uf.set_index("sigla_uf").loc[destaque]
    st.markdown(
        f"**{linha['nome_uf']}** ocupa a **{posicao}ª posição** entre as 27 UFs em "
        f"{metrica.rotulo_frase}: {fmt(linha[coluna], metrica.casas)} {metrica.unidade}."
    )

st.caption(
    "Troque a métrica na barra lateral: estados que lideram em valores absolutos "
    "nem sempre lideram quando a adoção é dividida pela população."
)
rodape()
