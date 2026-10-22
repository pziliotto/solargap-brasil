"""
PROJETO: SolarGap Brasil
ARQUIVO: paginas/evolucao.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026 (origem: aba Evolução do demo_app.py, TP2)
ATUALIZAÇÃO:

DESCRIÇÃO:
    Duas leituras do tempo:
        1. Série de conexões — potência ou empreendimentos por ano (TP2);
        2. Taxa de crescimento — KPI que no TP2 estava parcial e agora está
           completo: crescimento anual do parque instalado e crescimento médio
           (CAGR) de cada UF em uma janela escolhida pelo usuário.

DEFINIÇÕES (ver src/servicos/indicadores.py):
    Crescimento anual = potência acumulada no fim do ano / no fim do ano
    anterior - 1. O acumulado sempre parte do início da série, mesmo que o
    filtro de período comece depois: o estoque de 2024 inclui tudo o que foi
    conectado antes.
"""

import plotly.express as px
import streamlit as st

from src.app import carregamento as dados
from src.app.componentes import (
    COR_BASE,
    COR_DESTAQUE,
    SIGLAS,
    faixa_ano_parcial,
    filtros_atuais,
    fmt,
    rodape,
    widget_persistente,
)
from src.preparacao import esquema
from src.servicos import indicadores

filtros = filtros_atuais()
agregado = dados.carregar_agregado()
indicadores_uf = dados.indicadores_por_uf(
    agregado,
    dados.carregar_uf(),
    filtros.ano_inicio,
    filtros.ano_fim,
    filtros.classes,
    filtros.incluir_imputados,
)

st.title("📈 Evolução e crescimento")
st.caption(f"Visão: {filtros.visao}")

# UFs da comparação: a UF em destaque (Panorama) ou as 3 líderes na métrica
destaque = st.session_state.get("_uf_destaque", "Nenhuma")
padrao = (
    [destaque]
    if destaque != "Nenhuma"
    else indicadores_uf.nlargest(3, filtros.metrica)["sigla_uf"].tolist()
)
ufs = widget_persistente(st.multiselect, "UFs", "ufs_evolucao", padrao, options=SIGLAS)

aba_serie, aba_crescimento = st.tabs(["Conexões por ano", "Taxa de crescimento"])

# ═══════════════════ 1. Série de conexões ═══════════════════

with aba_serie:
    c1, c2 = st.columns(2)
    medida = c1.radio(
        "Medida",
        ["Potência (MW)", "Empreendimentos"],
        horizontal=True,
        key="medida_evolucao",
    )
    modo = c2.radio(
        "Modo", ["Anual", "Acumulado no período"], horizontal=True, key="modo_evolucao"
    )

    if not ufs:
        st.info("Escolha ao menos uma UF.")
    else:
        serie = dados.serie_anual(
            agregado,
            filtros.ano_inicio,
            filtros.ano_fim,
            filtros.classes,
            filtros.incluir_imputados,
        )
        coluna = "potencia_mw" if medida == "Potência (MW)" else "qtd_empreendimentos"
        serie = serie[serie["sigla_uf"].isin(ufs)].sort_values(["sigla_uf", "ano"])
        if modo == "Acumulado no período":
            serie[coluna] = serie.groupby("sigla_uf")[coluna].cumsum()

        figura = px.line(
            serie,
            x="ano",
            y=coluna,
            color="sigla_uf",
            markers=True,
            labels={"ano": "Ano de conexão", coluna: medida, "sigla_uf": "UF"},
        )
        faixa_ano_parcial(figura, filtros.ano_fim)
        figura.update_layout(height=460, margin=dict(t=40, b=10), xaxis=dict(dtick=1))
        st.plotly_chart(figura, width="stretch")
        st.caption(
            "A retração de 2023 acompanha a corrida por conexões antes do fim da isenção do "
            "Fio B, em janeiro de 2023. O acumulado conta a partir do primeiro ano do filtro."
        )

# ═══════════════════ 2. Taxa de crescimento ═══════════════════

with aba_crescimento:
    st.markdown(
        "Crescimento do **parque instalado** (potência acumulada). Diferente da série de "
        "conexões: em 2023 entraram menos sistemas que em 2022, mas o parque continuou crescendo."
    )

    serie_estoque = dados.serie_acumulada(
        agregado, filtros.classes, filtros.incluir_imputados
    )
    anos_completos = list(range(esquema.ANO_MINIMO, esquema.ANO_PARCIAL))

    if ufs:
        recorte = serie_estoque[
            serie_estoque["sigla_uf"].isin(ufs)
            & serie_estoque["ano"].between(
                max(filtros.ano_inicio, 2016), filtros.ano_fim
            )
        ]
        figura = px.line(
            recorte,
            x="ano",
            y="crescimento_pct",
            color="sigla_uf",
            markers=True,
            labels={
                "ano": "Ano",
                "crescimento_pct": "Crescimento do parque (%)",
                "sigla_uf": "UF",
            },
        )
        faixa_ano_parcial(figura, filtros.ano_fim)
        figura.update_layout(height=380, margin=dict(t=30, b=10), xaxis=dict(dtick=1))
        st.plotly_chart(figura, width="stretch")
        st.caption(
            "A série começa em 2016: antes disso, bases de poucos kW geram taxas de milhares "
            f"de por cento, sem significado. {esquema.ANO_PARCIAL} cobre só até agosto."
        )

    st.subheader("Crescimento médio anual (CAGR) por UF")
    c1, c2 = st.columns(2)
    ano_base = c1.selectbox(
        "Ano base",
        anos_completos[:-1],
        index=anos_completos.index(indicadores.ANO_BASE_CRESCIMENTO),
        key="ano_base_cagr",
        help="Padrão 2022: ano da Lei 14.300, recorte central do projeto.",
    )
    finais = [a for a in anos_completos if a > ano_base]
    ano_final = c2.selectbox(
        "Ano final", finais, index=len(finais) - 1, key="ano_final_cagr"
    )

    tabela, cagr_brasil = dados.taxa_crescimento(
        agregado, filtros.classes, filtros.incluir_imputados, ano_base, ano_final
    )
    tabela = tabela.merge(
        indicadores_uf[["sigla_uf", "nome_uf", "regiao"]], on="sigla_uf"
    ).sort_values("cagr_pct")

    figura = px.bar(
        tabela,
        x="cagr_pct",
        y="sigla_uf",
        orientation="h",
        hover_data={
            "nome_uf": True,
            "acumulado_base_mw": ":.1f",
            "acumulado_final_mw": ":.1f",
        },
        labels={"cagr_pct": "CAGR (% ao ano)", "sigla_uf": "UF"},
    )
    figura.update_traces(
        marker_color=[
            COR_DESTAQUE if s in ufs else COR_BASE for s in tabela["sigla_uf"]
        ]
    )
    figura.add_vline(
        x=cagr_brasil,
        line_dash="dash",
        line_color="gray",
        annotation_text=f"Brasil: {fmt(cagr_brasil, 1)}%",
        annotation_position="top",
    )
    figura.update_layout(height=720, yaxis_title=None, margin=dict(t=40, b=10))
    st.plotly_chart(figura, width="stretch")

    mais_rapida = tabela.iloc[-1]
    st.markdown(
        f"De {ano_base} a {ano_final}, o parque solar distribuído do Brasil cresceu em média "
        f"**{fmt(cagr_brasil, 1)}% ao ano**. A expansão mais rápida foi em "
        f"**{mais_rapida['nome_uf']}** ({fmt(mais_rapida['cagr_pct'], 1)}% ao ano)."
    )
    st.caption(
        "UFs com parque pequeno no ano base tendem a exibir taxas altas: compare sempre com "
        "a potência absoluta (passe o mouse sobre as barras)."
    )

rodape()
