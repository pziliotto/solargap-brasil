"""
PROJETO: SolarGap Brasil
ARQUIVO: demo_app.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 20/08/2026
ATUALIZAÇÃO: 21/09/2026 — TP2: abas interativas, cache, estado de sessão,
             notícias (web scraping) e upload/download de CSV

DESCRIÇÃO:
    Dashboard do SolarGap Brasil. Lê exclusivamente a camada Gold
    (data/processed), o que permite rodar sem a base completa da ANEEL.

ESTRUTURA:
    Barra lateral — filtros globais (visão, métrica, período, classe)
    Aba Panorama  — KPIs e ranking das UFs com destaque de uma UF
    Aba Evolução  — série anual ou acumulada por UF
    Aba Notícias  — corpus coletado da Agência Brasil: nuvem, termos, tabela
    Aba Dados     — download dos recortes e upload de indicador do usuário

    No TP3, cada aba vira uma página do app multipáginas.

ESTADO DE SESSÃO:
    - filtros da barra lateral e UF em destaque: persistem entre abas e
      interações (widgets com key);
    - arquivo enviado pelo usuário: validado uma única vez e guardado em
      st.session_state até ser removido.

OBS. DE USO:
    Rodar a partir da raiz:
        python -m streamlit run src/app/demo_app.py
"""

import sys
from pathlib import Path

# Garante que a raiz do projeto esteja no path (este arquivo está em src/app/)
RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import pandas as pd
import plotly.express as px
import streamlit as st

from src.app import carregamento as dados
from src.app.validacao_upload import gerar_modelo, validar_upload
from src.preparacao import esquema

# ═══════════════════ Configuração ═══════════════════

st.set_page_config(page_title="SolarGap - Brasil", page_icon="☀️", layout="wide")

METRICAS = {
    "Watts por habitante": ("watts_por_habitante", "W/hab", 1),
    "Empreendimentos por 100 mil hab.": (
        "empreendimentos_por_100k_hab",
        "por 100 mil hab.",
        1,
    ),
    "Potência instalada (MW)": ("potencia_mw", "MW", 1),
    "Número de empreendimentos": ("qtd_empreendimentos", "empreendimentos", 0),
}
METRICAS_PER_CAPITA = {"watts_por_habitante", "empreendimentos_por_100k_hab"}
VISOES = {"Com correção de preenchimento": True, "Critério ANEEL": False}

COR_DESTAQUE = "#F4A300"
COR_BASE = "#B8C2CC"
SIGLAS = sorted(esquema.UFS)


def fmt(valor: float, casas: int = 0) -> str:
    """Formato brasileiro: 1234567.8 -> 1.234.567,8"""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def para_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")


# ═══════════════════ Dados ═══════════════════

agregado = dados.carregar_agregado()
dim_uf = dados.carregar_uf()
corpus = dados.carregar_corpus()

ANO_MIN, ANO_MAX = int(agregado["ano"].min()), int(agregado["ano"].max())
CLASSES = sorted(agregado["classe_consumo"].unique())

st.session_state.setdefault("upload", None)

# ═══════════════════ Barra lateral ═══════════════════

with st.sidebar:
    st.header("Filtros")

    visao = st.radio(
        "Visão dos dados",
        list(VISOES),
        key="visao",
        help=(
            "Uma distribuidora do Maranhão não informa a fonte de geração em cerca de "
            "73 mil registros. 'Com correção' os conta como solares (99,98% dos registros "
            "com fonte conhecida são solares); 'Critério ANEEL' os exclui, como o painel oficial."
        ),
    )
    nome_metrica = st.selectbox("Métrica", list(METRICAS), key="metrica")
    ano_inicio, ano_fim = st.slider(
        "Ano de conexão", ANO_MIN, ANO_MAX, (ANO_MIN, ANO_MAX), key="periodo"
    )
    classes = st.multiselect(
        "Classe de consumo", CLASSES, default=CLASSES, key="classes"
    )

    if ano_fim >= esquema.ANO_PARCIAL:
        st.caption(f"⚠️ {esquema.ANO_PARCIAL} é parcial: dados até agosto.")

    st.divider()
    st.markdown(
        """
**Inspirações do projeto**
- [ODS 7 — Energia limpa e acessível (ONU Brasil)](https://brasil.un.org/pt-br/sdgs/7)
- [Desertec — o debate sobre energia solar no Saara](https://www.desertec.org)
- [EPE — estudos de micro e minigeração distribuída](https://www.epe.gov.br)

**Contexto regulatório**
- [Lei 14.300/2022](https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/lei/l14300.htm)
"""
    )

if not classes:
    st.warning("Selecione ao menos uma classe de consumo na barra lateral.")
    st.stop()

incluir_imputados = VISOES[visao]
coluna, unidade, casas = METRICAS[nome_metrica]
indicadores = dados.indicadores_por_uf(
    agregado, dim_uf, ano_inicio, ano_fim, tuple(classes), incluir_imputados
)

# ═══════════════════ Cabeçalho ═══════════════════

st.title(":green[SolarGap - Brasil]")
st.caption("Onde está o próximo mercado solar?")

with st.expander("Sobre o projeto"):
    st.markdown(
        """
**O problema.** Desde a promulgação da Lei 14.300/2022 (Marco Legal da Geração Distribuída),
a geração distribuída de energia solar cresceu de forma acentuada no Brasil. No entanto, há
indícios de que esse crescimento não se distribui de forma equânime entre os estados — o que
pode aprofundar desigualdades regionais de acesso à transição energética.

**O objetivo.** Mapear e quantificar essa disparidade a partir de dados públicos da ANEEL e do
IBGE, identificando quais estados lideram e quais ficam para trás na adoção de energia solar
distribuída — e onde estão as oportunidades ainda não exploradas pelo mercado solar.
"""
    )

imputados_no_recorte = int(indicadores["qtd_imputados"].sum())
if incluir_imputados and imputados_no_recorte:
    st.info(
        f"Esta visão inclui {fmt(imputados_no_recorte)} registros sem fonte informada "
        "(quase todos no Maranhão), contados como solares. Alterne para **Critério ANEEL** "
        "na barra lateral para reproduzir os números do painel oficial.",
        icon="ℹ️",
    )

aba_panorama, aba_evolucao, aba_noticias, aba_dados = st.tabs(
    ["📊 Panorama", "📈 Evolução", "📰 Notícias", "📁 Dados"]
)

# ═══════════════════ Aba Panorama ═══════════════════

with aba_panorama:
    total_kw = indicadores["potencia_kw"].sum()
    total_qtd = indicadores["qtd_empreendimentos"].sum()
    total_pop = indicadores["populacao"].sum()
    media_brasil = {
        "watts_por_habitante": total_kw * 1_000 / total_pop,
        "empreendimentos_por_100k_hab": total_qtd / total_pop * 100_000,
    }
    lider = indicadores.sort_values(coluna, ascending=False).iloc[0]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Potência instalada", f"{fmt(total_kw / 1_000, 1)} MW")
    k2.metric("Empreendimentos", fmt(total_qtd))
    k3.metric("Média Brasil", f"{fmt(media_brasil['watts_por_habitante'], 1)} W/hab")
    k4.metric(f"Líder em {nome_metrica.lower()}", lider["nome_uf"])

    uf_destaque = st.selectbox(
        "Destacar uma UF no ranking", ["Nenhuma"] + SIGLAS, key="uf_destaque"
    )

    ordenado = indicadores.sort_values(coluna, ascending=True)
    rotulos = {
        coluna: f"{nome_metrica}",
        "sigla_uf": "UF",
        "regiao": "Região",
        "nome_uf": "Estado",
    }

    if uf_destaque == "Nenhuma":
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
                COR_DESTAQUE if s == uf_destaque else COR_BASE
                for s in ordenado["sigla_uf"]
            ]
        )

    if coluna in METRICAS_PER_CAPITA:
        figura.add_vline(
            x=media_brasil[coluna],
            line_dash="dash",
            line_color="gray",
            annotation_text="Média Brasil",
            annotation_position="top",
        )

    figura.update_layout(
        height=720, yaxis_title=None, margin=dict(t=40, b=10), legend_title=None
    )
    st.plotly_chart(figura, width="stretch")

    if uf_destaque != "Nenhuma":
        ranking = indicadores.sort_values(coluna, ascending=False).reset_index(
            drop=True
        )
        posicao = int(ranking.index[ranking["sigla_uf"] == uf_destaque][0]) + 1
        linha = ranking.iloc[posicao - 1]
        st.markdown(
            f"**{linha['nome_uf']}** ocupa a **{posicao}ª posição** entre as 27 UFs em "
            f"{nome_metrica.lower()}: {fmt(linha[coluna], casas)} {unidade}."
        )

    st.caption(
        "Troque a métrica na barra lateral: estados que lideram em valores absolutos "
        "nem sempre lideram quando a adoção é dividida pela população."
    )

# ═══════════════════ Aba Evolução ═══════════════════

with aba_evolucao:
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

    padrao = (
        [st.session_state["uf_destaque"]]
        if st.session_state.get("uf_destaque", "Nenhuma") != "Nenhuma"
        else indicadores.nlargest(3, coluna)["sigla_uf"].tolist()
    )
    ufs_escolhidas = st.multiselect("UFs", SIGLAS, default=padrao, key="ufs_evolucao")

    if not ufs_escolhidas:
        st.info("Escolha ao menos uma UF.")
    else:
        serie = dados.serie_anual(
            agregado, ano_inicio, ano_fim, tuple(classes), incluir_imputados
        )
        coluna_medida = (
            "potencia_mw" if medida == "Potência (MW)" else "qtd_empreendimentos"
        )
        serie = serie[serie["sigla_uf"].isin(ufs_escolhidas)].sort_values(
            ["sigla_uf", "ano"]
        )

        if modo == "Acumulado no período":
            serie[coluna_medida] = serie.groupby("sigla_uf")[coluna_medida].cumsum()

        figura = px.line(
            serie,
            x="ano",
            y=coluna_medida,
            color="sigla_uf",
            markers=True,
            labels={"ano": "Ano de conexão", coluna_medida: medida, "sigla_uf": "UF"},
        )
        if ano_fim >= esquema.ANO_PARCIAL:
            figura.add_vrect(
                x0=esquema.ANO_PARCIAL - 0.5,
                x1=esquema.ANO_PARCIAL + 0.5,
                fillcolor="gray",
                opacity=0.15,
                line_width=0,
                annotation_text="parcial",
                annotation_position="top left",
            )
        figura.update_layout(height=480, margin=dict(t=40, b=10), xaxis=dict(dtick=1))
        st.plotly_chart(figura, width="stretch")

        st.caption(
            "A retração de 2023 acompanha a corrida por conexões antes do fim da isenção do "
            "Fio B, em janeiro de 2023. O acumulado conta a partir do primeiro ano do filtro."
        )

# ═══════════════════ Aba Notícias ═══════════════════

with aba_noticias:
    st.markdown(
        f"Corpus de **{len(corpus)} notícias** sobre energia solar e geração distribuída, "
        "coletadas da Agência Brasil por web scraping."
    )

    frequencias_gerais = dados.frequencia_termos(tuple(corpus["texto"].fillna("")))
    termos_frequentes = sorted(
        frequencias_gerais, key=frequencias_gerais.get, reverse=True
    )[:40]

    c1, c2 = st.columns(2)
    uf_noticia = c1.selectbox(
        "Notícias que mencionam", ["Todas as UFs"] + SIGLAS, key="uf_noticia"
    )
    ocultar = c2.multiselect(
        "Ocultar termos da nuvem",
        sorted(set(termos_frequentes) | {"energia", "solar"}),
        default=["energia", "solar"],
        key="termos_ocultos",
        help="Os termos do próprio tema dominam a nuvem e escondem o resto.",
    )

    if uf_noticia == "Todas as UFs":
        selecao = corpus
    else:
        selecao = corpus[
            corpus["ufs_mencionadas"]
            .str.split(",")
            .apply(lambda ufs: uf_noticia in ufs)
        ]

    if selecao.empty:
        st.info("Nenhuma notícia menciona essa UF.")
    else:
        k1, k2, k3 = st.columns(3)
        k1.metric("Notícias", len(selecao))
        k2.metric(
            "Período",
            f"{selecao['data_publicacao'].min():%Y} – {selecao['data_publicacao'].max():%Y}",
        )
        k3.metric(
            "Tamanho médio", f"{fmt(selecao['texto'].str.len().mean())} caracteres"
        )

        frequencias = dados.frequencia_termos(tuple(selecao["texto"].fillna("")))
        frequencias = {t: n for t, n in frequencias.items() if t not in ocultar}
        mais_frequentes = dict(
            sorted(frequencias.items(), key=lambda item: item[1], reverse=True)[:150]
        )

        col_nuvem, col_termos = st.columns([3, 2])
        with col_nuvem:
            st.subheader("Nuvem de palavras")
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
            st.subheader("Notícias por ano")
            por_ano = selecao["data_publicacao"].dt.year.value_counts().sort_index()
            figura = px.bar(
                x=por_ano.index, y=por_ano.values, labels={"x": "Ano", "y": "Notícias"}
            )
            figura.update_layout(
                height=320, margin=dict(t=10, b=10), xaxis=dict(dtick=1)
            )
            st.plotly_chart(figura, width="stretch")
        with col_uf:
            st.subheader("UFs mais mencionadas")
            mencoes = (
                corpus["ufs_mencionadas"]
                .str.split(",")
                .explode()
                .loc[lambda s: s != ""]
                .value_counts()
                .head(10)
            )
            figura = px.bar(
                x=mencoes.values[::-1],
                y=mencoes.index[::-1],
                orientation="h",
                labels={"x": "Notícias", "y": "UF"},
            )
            figura.update_layout(height=320, margin=dict(t=10, b=10))
            st.plotly_chart(figura, width="stretch")
            st.caption(
                "Compare a atenção da imprensa com o ranking de adoção da aba Panorama."
            )

        st.subheader("Notícias")
        st.dataframe(
            selecao[["data_publicacao", "titulo", "ufs_mencionadas", "url"]],
            column_config={
                "data_publicacao": st.column_config.DateColumn(
                    "Data", format="DD/MM/YYYY"
                ),
                "titulo": st.column_config.TextColumn("Título", width="large"),
                "ufs_mencionadas": "UFs mencionadas",
                "url": st.column_config.LinkColumn("Link", display_text="abrir"),
            },
            hide_index=True,
            width="stretch",
        )

    st.caption(
        "Fonte: Agência Brasil (EBC). Reprodução autorizada mediante indicação da fonte."
    )

# ═══════════════════ Aba Dados ═══════════════════

with aba_dados:
    st.subheader("Download")
    st.markdown("Os arquivos respeitam os filtros aplicados na barra lateral.")

    d1, d2, d3 = st.columns(3)
    d1.download_button(
        "Indicadores por UF",
        para_csv(indicadores.drop(columns=["potencia_kw"])),
        file_name="solargap_indicadores_uf.csv",
        mime="text/csv",
        width="stretch",
    )
    d2.download_button(
        "Série anual por UF",
        para_csv(
            dados.serie_anual(
                agregado, ano_inicio, ano_fim, tuple(classes), incluir_imputados
            )
        ),
        file_name="solargap_serie_anual.csv",
        mime="text/csv",
        width="stretch",
    )
    d3.download_button(
        "Corpus de notícias",
        para_csv(corpus),
        file_name="solargap_noticias.csv",
        mime="text/csv",
        width="stretch",
    )

    st.divider()
    st.subheader("Compare com um indicador seu")
    st.markdown(
        "Envie um CSV com um valor por UF — carteira de clientes, instaladores, metas — "
        "para compará-lo com a adoção de energia solar. Baixe o modelo, preencha a coluna "
        "`valor` (pode renomeá-la) e envie o arquivo."
    )

    st.download_button(
        "Baixar modelo (CSV)",
        gerar_modelo(),
        file_name="modelo_solargap.csv",
        mime="text/csv",
    )
    arquivo = st.file_uploader("Enviar CSV", type=["csv"], key="arquivo_usuario")

    # Valida só quando chega um arquivo novo; o resultado fica na sessão.
    if arquivo is not None:
        atual = st.session_state["upload"]
        if atual is None or atual["file_id"] != arquivo.file_id:
            st.session_state["upload"] = {
                "file_id": arquivo.file_id,
                "nome": arquivo.name,
                "resultado": validar_upload(arquivo.getvalue()),
            }

    enviado = st.session_state["upload"]
    if enviado is not None:
        resultado = enviado["resultado"]
        st.markdown(f"Arquivo na sessão: **{enviado['nome']}**")

        for erro in resultado.erros:
            st.error(erro)
        for aviso in resultado.avisos:
            st.warning(aviso)

        if resultado.dados is not None:
            valor = resultado.coluna_valor
            cruzado = indicadores.merge(resultado.dados, on="sigla_uf", how="inner")

            figura = px.scatter(
                cruzado,
                x=valor,
                y=coluna,
                text="sigla_uf",
                color="regiao",
                labels={valor: valor, coluna: nome_metrica, "regiao": "Região"},
            )
            figura.update_traces(textposition="top center")
            figura.update_layout(height=480, margin=dict(t=20, b=10))
            st.plotly_chart(figura, width="stretch")
            st.caption(
                f"UFs com {nome_metrica.lower()} alta e {valor} baixo são candidatas a "
                "mercado ainda pouco explorado."
            )

            tabela = cruzado[["sigla_uf", "nome_uf", valor, coluna]].sort_values(
                coluna, ascending=False
            )
            st.dataframe(tabela, hide_index=True, width="stretch")
            st.download_button(
                "Baixar comparação",
                para_csv(tabela),
                file_name="solargap_comparacao.csv",
                mime="text/csv",
            )

        if st.button("Remover arquivo da sessão"):
            st.session_state["upload"] = None
            st.rerun()

st.divider()
st.caption(
    "Fontes: ANEEL — Relação de Empreendimentos de MMGD (ODbL) · IBGE — Censo 2022 · "
    "Agência Brasil (EBC). Metodologia e decisões de tratamento no Data Summary Report."
)
