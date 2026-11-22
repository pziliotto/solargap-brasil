"""
PROJETO: SolarGap Brasil
ARQUIVO: paginas/potencial.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026

DESCRIÇÃO:
    Página "Potencial Solar" (TP4.5, Tarefa 7), pensada para gestão: quanto do
    potencial técnico residencial já é aproveitado em cada UF e município, a
    que fatores o gap está associado e como a irradiação pode mudar até 2050.

CONTEÚDO:
    - filtros de UF e município (persistentes entre páginas);
    - cards: potencial (x), produção estimada (y), gap (x − y) e % realizado;
    - waterfall SHAP do recorte, do maior para o menor efeito;
    - mapa coroplético da taxa de realização (UFs ou municípios da UF);
    - tabela-heatmap UFs x (irradiação, taxa, gap, principais fatores);
    - matriz de correlação de Spearman;
    - aba "Cenários 2030–2050" (SSP2-4.5 / SSP5-8.5, com faixa de incerteza);
    - nota de metodologia.

VISÃO:
    Segue o seletor da barra lateral (corrigida, ANEEL ou conservadora),
    desenhado pelo app.py em todas as páginas.

REGRA DE NEGÓCIO:
    Toda em src/servicos/potencial.py, a mesma das rotas /potencial da API.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.app import carregamento as dados
from src.app.componentes import (
    SIGLAS,
    VISOES,
    fmt,
    link_doc,
    para_csv,
    rodape,
    visao_atual,
    widget_persistente,
)
from src.preparacao import esquema
from src.servicos import potencial
from src.servicos.dados import DadosIndisponiveis

# Paleta: sequencial de um só tom (azul) para a taxa; divergente azul x vermelho
# com meio cinza para sinais (SHAP, correlação, variação da irradiação).
SEQUENCIAL = [
    "#cde2fb",
    "#9ec5f4",
    "#6da7ec",
    "#3987e5",
    "#256abf",
    "#184f95",
    "#0d366b",
]
DIVERGENTE = [[0.0, "#b22b2a"], [0.5, "#f0efec"], [1.0, "#1c5cab"]]
COR_ELEVA = "#256abf"
COR_REDUZ = "#c62828"
COR_TOTAL = "#8a8f98"
N_FATORES_WATERFALL = 8


def energia(mwh: float) -> str:
    """MWh/ano com a unidade que deixa o número legível."""
    if mwh is None or pd.isna(mwh):
        return "—"
    if abs(mwh) >= 1e6:
        return f"{fmt(mwh / 1e6, 1)} TWh/ano"
    if abs(mwh) >= 1e3:
        return f"{fmt(mwh / 1e3, 1)} GWh/ano"
    return f"{fmt(mwh, 0)} MWh/ano"


def pct(valor: float, casas: int = 1) -> str:
    return "—" if valor is None or pd.isna(valor) else f"{fmt(valor * 100, casas)}%"


def pp(valor_pp: float) -> str:
    """Pontos percentuais com sinal: +5,6 p.p. / −7,7 p.p."""
    return f"{'+' if valor_pp >= 0 else '−'}{fmt(abs(valor_pp), 1)} p.p."


def pct_sinal(valor: float) -> str:
    return f"{'+' if valor >= 0 else '−'}{fmt(abs(valor) * 100, 1)}%"


# ═══════════════════ Carga e filtros ═══════════════════

visao = visao_atual()
try:
    base = dados.carregar_base_potencial()
except DadosIndisponiveis as erro:
    st.error(f"Não foi possível carregar a Gold de potencial: {erro}")
    st.stop()

st.title("🏠 Potencial Solar")
st.caption(
    f"Potencial técnico residencial x produção da micro e minigeração residencial e rural · "
    f"base ANEEL 10/{esquema.ANO_PARCIAL} ({esquema.ANO_PARCIAL} parcial, até outubro) · "
    f"visão: {VISOES[visao]}"
)

f1, f2 = st.columns(2)
with f1:
    uf = widget_persistente(
        st.selectbox, "UF", "pot_uf", "Brasil", options=["Brasil"] + SIGLAS
    )
uf = None if uf == "Brasil" else uf
municipios = potencial.municipios_da_uf(base, uf) if uf else pd.DataFrame()
nomes = dict(zip(municipios.get("cod_ibge", []), municipios.get("nome", [])))
opcoes_municipio = ["todos", *nomes]
if st.session_state.get("_pot_municipio") not in opcoes_municipio:
    st.session_state["_pot_municipio"] = "todos"  # UF mudou: volta para "todos"
with f2:
    cod_ibge = widget_persistente(
        st.selectbox,
        "Município",
        "pot_municipio",
        "todos",
        options=opcoes_municipio,
        format_func=lambda c: "Todos os municípios" if c == "todos" else nomes[c],
        disabled=uf is None,
        help="Escolha uma UF para listar os municípios.",
    )
cod_ibge = None if cod_ibge == "todos" else cod_ibge

resumo = dados.resumo_potencial(base, visao, uf, cod_ibge)

# ═══════════════════ Cards ═══════════════════

st.subheader(resumo["nome"])
k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "Potencial (x)",
    energia(resumo["x_mwh_ano"]),
    help="Geração possível nos telhados residenciais: domicílios x 15 m² úteis x "
    "eficiência de 20% x irradiação x PR de 0,75 x 365 dias.",
)
k2.metric(
    "Produção estimada (y)",
    energia(resumo["y_mwh_ano"]),
    help="Geração estimada da MMGD residencial e rural com geração na própria unidade "
    "consumidora, com a mesma irradiação e o mesmo PR.",
)
k3.metric(
    "Gap (x − y)",
    energia(resumo["gap_mwh_ano"]),
    help="Potencial ainda não aproveitado. Negativo quando y > x.",
)
k4.metric(
    "% realizado",
    pct(resumo["taxa_realizacao"]),
    help="Taxa de realização: y / x. Em UF e Brasil, Σy / Σx.",
)
if resumo["taxa_realizacao"] > 1:
    st.warning(
        "Produção estimada acima do potencial técnico: o telhado médio deste município "
        "provavelmente é maior que os 15 m² premissados (casas rurais ou de alto padrão). "
        "Não é adoção acima de 100%.",
        icon="⚠️",
    )
elif resumo["n_municipios_taxa_acima_1"]:
    st.caption(
        f"{fmt(resumo['n_municipios_taxa_acima_1'])} município(s) do recorte com y > x "
        "(telhado médio maior que o premissado)."
    )

aba_diagnostico, aba_cenarios, aba_metodologia = st.tabs(
    ["Diagnóstico atual", "Cenários 2030–2050", "Metodologia"]
)

# ═══════════════════ Diagnóstico ═══════════════════

with aba_diagnostico:
    explicacao = dados.explicacao_potencial(base, visao, uf, cod_ibge)
    st.markdown("#### O que explica a taxa")
    e1, e2, e3 = st.columns([1, 1, 2])
    e1.metric("Realiza", pct(explicacao["taxa_observada"]))
    e2.metric(
        "Esperado pelo perfil",
        pct(explicacao["taxa_prevista"]),
        help="Previsão do modelo a partir dos fatores medidos (renda, densidade, "
        "tarifa, irradiação etc.).",
    )
    e3.markdown(explicacao["comparacao_esperado"])

    grupos = explicacao["grupos"]
    baixo, cima = st.columns(2)
    for coluna, efeito, titulo in (
        (baixo, "reduz", "🔻 Puxam a taxa para baixo (aumentam o gap)"),
        (cima, "eleva", "🔺 Puxam a taxa para cima (reduzem o gap)"),
    ):
        with coluna:
            st.markdown(f"**{titulo}**")
            do_sinal = [
                g
                for g in grupos
                if g["efeito"] == efeito and abs(g["contribuicao_pp"]) >= 0.05
            ]
            if not do_sinal:
                st.caption("Nenhum fator medido.")
            for g in do_sinal:
                st.markdown(f"- {g['rotulo']}: **{pp(g['contribuicao_pp'])}**")
    if explicacao["aviso_visao"]:
        st.info(
            "As contribuições abaixo vêm do modelo treinado na visão corrigida, o único "
            "com explicação por município. No modelo ajustado à visão escolhida, os "
            f"fatores mais importantes são: {', '.join(explicacao['ranking_global_visao'][:3]).lower()}.",
            icon="ℹ️",
        )
    if not explicacao["usado_no_treino"]:
        st.caption(
            "Este município ficou fora do treino do modelo (y > x); a explicação é "
            "indicativa."
        )

    fatores = explicacao["fatores"]
    principais = fatores[:N_FATORES_WATERFALL]
    resto = sum(f["contribuicao"] for f in fatores[N_FATORES_WATERFALL:])
    rotulos = [
        "Média dos municípios",
        *[f"{f['rotulo_no_grupo']} ({f['valor_texto']})" for f in principais],
        "Demais fatores",
        "Taxa prevista",
    ]
    valores = [
        explicacao["valor_base"] * 100,
        *[f["contribuicao"] * 100 for f in principais],
        resto * 100,
        explicacao["taxa_prevista"] * 100,
    ]
    textos = [
        f"{fmt(valores[0], 1)}%",
        *[pp(v) for v in valores[1:-1]],
        f"{fmt(valores[-1], 1)}%",
    ]
    figura = go.Figure(
        go.Waterfall(
            orientation="h",
            measure=["absolute", *["relative"] * (len(principais) + 1), "total"],
            y=rotulos,
            x=valores,
            text=textos,
            textposition="outside",
            increasing={"marker": {"color": COR_ELEVA}},
            decreasing={"marker": {"color": COR_REDUZ}},
            totals={"marker": {"color": COR_TOTAL}},
            connector={"line": {"color": "#d0d4da", "width": 1}},
            hovertemplate="%{y}: %{text}<extra></extra>",
        )
    )
    figura.update_layout(
        height=120 + 38 * len(rotulos),
        margin={"l": 10, "r": 60, "t": 10, "b": 30},
        yaxis={"autorange": "reversed"},
        xaxis={"title": "Taxa de realização prevista (%)", "ticksuffix": "%"},
        showlegend=False,
    )
    st.plotly_chart(figura, width="stretch")
    st.caption(
        "Cada variável do modelo, com o rótulo do grupo. Azul: eleva a taxa prevista "
        "(reduz o gap). Vermelho: reduz a taxa (aumenta o gap). Pontos percentuais em "
        "relação à média dos municípios; na UF e no Brasil, média ponderada por "
        "domicílios. Os grupos acima somam as variáveis da mesma família (o SHAP é "
        "aditivo). **Associação, não causalidade.**"
    )
    with st.expander("Detalhe por variável"):
        for g in grupos:
            membros = [f for f in fatores if f["grupo"] == g["grupo"]]
            if len(membros) > 1:
                st.markdown(f"**{g['rotulo']}: {pp(g['contribuicao_pp'])}**")
                for f in membros:
                    st.markdown(f"  - {f['frase']}")
            else:
                st.markdown(f"- {membros[0]['frase']}")

    st.markdown("#### Mapa da taxa de realização")
    if uf is None:
        tabela_mapa = dados.tabela_potencial_uf(base, visao)
        chave, geo = "uf", dados.malha(None)
        tabela_mapa = tabela_mapa.assign(nome=tabela_mapa["uf"])
        st.caption("Por UF. Escolha uma UF no filtro para ver os municípios.")
    else:
        tabela_mapa = dados.taxa_municipios(base, uf, visao)
        chave, geo = "cod_ibge", dados.malha(uf)
        st.caption(f"Municípios de {uf}. Contornos simplificados (~500 m).")
    tabela_mapa = tabela_mapa.assign(
        taxa_pct=tabela_mapa["taxa_realizacao"] * 100,
        gap_texto=tabela_mapa["gap_mwh_ano"].map(energia),
    )
    teto = float(min(100.0, max(tabela_mapa["taxa_pct"].quantile(0.95), 1.0)))
    mapa = px.choropleth(
        tabela_mapa,
        geojson=geo,
        locations=chave,
        featureidkey=f"properties.{chave}",
        color="taxa_pct",
        color_continuous_scale=SEQUENCIAL,
        range_color=(0, teto),
        hover_name="nome",
        hover_data={chave: False, "taxa_pct": ":.1f", "gap_texto": True},
        labels={"taxa_pct": "% realizado", "gap_texto": "Gap"},
    )
    mapa.update_geos(fitbounds="locations", visible=False)
    mapa.update_traces(marker_line_width=0.3, marker_line_color="#ffffff")
    if cod_ibge:
        destaque = tabela_mapa[tabela_mapa["cod_ibge"] == cod_ibge]
        mapa.add_trace(
            go.Choropleth(
                geojson=geo,
                locations=destaque["cod_ibge"],
                featureidkey="properties.cod_ibge",
                z=[1] * len(destaque),
                colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
                showscale=False,
                marker_line_width=2.5,
                marker_line_color="#F4A300",
                hoverinfo="skip",
            )
        )
    mapa.update_layout(
        height=520,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        coloraxis_colorbar={"title": "% realizado", "ticksuffix": "%"},
    )
    st.plotly_chart(mapa, width="stretch")
    if teto < tabela_mapa["taxa_pct"].max():
        st.caption(
            f"Escala de cor limitada a {fmt(teto, 0)}% (percentil 95) para não deixar "
            "os extremos apagarem o contraste."
        )

    st.markdown("#### UFs lado a lado")
    tabela = dados.tabela_potencial_uf(base, visao)
    heatmap = pd.DataFrame(
        {
            "UF": tabela["uf"],
            "Irradiação (kWh/m²/dia)": tabela["irradiacao_kwh_m2_dia"],
            "% realizado": tabela["taxa_realizacao"] * 100,
            "Gap (GWh/ano)": tabela["gap_mwh_ano"] / 1e3,
            "Principais fatores (efeito na taxa)": tabela["principais_fatores"].map(
                " · ".join
            ),
        }
    )
    estilo = (
        heatmap.style.background_gradient(
            cmap="Blues", subset=["Irradiação (kWh/m²/dia)", "% realizado"]
        )
        .background_gradient(cmap="Oranges", subset=["Gap (GWh/ano)"])
        .format(
            {
                "Irradiação (kWh/m²/dia)": lambda v: fmt(v, 2),
                "% realizado": lambda v: fmt(v, 1),
                "Gap (GWh/ano)": lambda v: fmt(v, 0),
            }
        )
    )
    if uf:
        estilo = estilo.apply(
            lambda linha: [
                "font-weight: bold" if linha["UF"] == uf else "" for _ in linha
            ],
            axis=1,
        )
    st.dataframe(estilo, hide_index=True, width="stretch", height=38 * 28)
    st.caption(
        "Principais fatores: os três grupos de maior contribuição SHAP (em valor "
        "absoluto) da UF. '+' eleva a taxa (reduz o gap); '−' reduz a taxa (aumenta o "
        "gap). Gap em GWh/ano."
    )
    st.download_button(
        "Baixar tabela por UF (CSV)",
        para_csv(
            tabela.assign(
                principais_fatores=tabela["principais_fatores"].map(" · ".join)
            )
        ),
        file_name=f"potencial_uf_{visao}.csv",
        mime="text/csv",
    )

    st.markdown("#### Correlação entre a taxa e os fatores")
    matriz = potencial.matriz_correlacao(base)
    correlacao = px.imshow(
        matriz,
        zmin=-1,
        zmax=1,
        color_continuous_scale=DIVERGENTE,
        text_auto=".2f",
        aspect="auto",
    )
    correlacao.update_layout(
        height=640,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        coloraxis_colorbar={"title": "ρ"},
    )
    correlacao.update_xaxes(tickangle=-40)
    st.plotly_chart(correlacao, width="stretch")
    st.caption(
        "Correlação de Spearman entre os municípios (visão corrigida, Tarefa 4). Azul: "
        "crescem juntos; vermelho: um cresce quando o outro cai. Fatores muito "
        "correlacionados entre si (as duas rendas, por exemplo) dividem o crédito no SHAP."
    )

# ═══════════════════ Cenários 2030–2050 ═══════════════════

with aba_cenarios:
    st.info(potencial.AVISO_CENARIOS, icon="🌦️")
    cenario = widget_persistente(
        st.radio,
        "Cenário de emissões",
        "pot_cenario",
        "ssp245",
        options=list(potencial.CENARIOS),
        format_func=potencial.CENARIOS.get,
        horizontal=True,
    )

    if cod_ibge:
        projecao = dados.cenarios_municipio(base, cod_ibge, visao)
        titulo = resumo["nome"]
    else:
        projecao = dados.cenarios_uf(base, visao, uf)
        titulo = uf or "Brasil"
    projecao_cenario = projecao[projecao["cenario"] == cenario]

    if uf or cod_ibge:
        st.markdown(f"##### {titulo}")
        for _, linha in projecao_cenario.iterrows():
            c1, c2, c3 = st.columns(3)
            c1.metric(
                f"Irradiação {linha['janela']}",
                f"{pct_sinal(linha['delta_mediano'])}",
                help="Mediana dos 5 modelos; faixa abaixo (mín.–máx.).",
                delta_color="off",
            )
            c1.caption(
                f"Faixa: {pct_sinal(linha['delta_min'])} a {pct_sinal(linha['delta_max'])}"
            )
            c2.metric(
                f"Potencial (x) {linha['janela']}",
                energia(linha["x_projetado_mwh_ano"]),
            )
            c2.caption(
                f"Faixa: {energia(linha['x_projetado_min_mwh_ano'])} a "
                f"{energia(linha['x_projetado_max_mwh_ano'])}"
            )
            c3.metric(f"Gap {linha['janela']}", energia(linha["gap_projetado_mwh_ano"]))
            c3.caption(
                f"Faixa: {energia(linha['gap_projetado_min_mwh_ano'])} a "
                f"{energia(linha['gap_projetado_max_mwh_ano'])}"
            )
        st.caption(
            f"% realizado atual: {pct(projecao_cenario['taxa_realizacao'].iloc[0])}. "
            "Com a potência instalada fixa, o % realizado do município não muda com a "
            "irradiação (H se cancela em y / x); na UF, muda só pela composição."
        )
        if cod_ibge and projecao["distancia_celula_km"].iloc[0] > 30:
            st.warning(
                f"Município a {fmt(projecao['distancia_celula_km'].iloc[0], 0)} km da "
                "célula do modelo climático com dado: leia o delta com cautela.",
                icon="⚠️",
            )

    st.markdown("##### Variação da irradiação por UF")
    por_uf = dados.cenarios_uf(base, visao, None)
    por_uf = por_uf[por_uf["cenario"] == cenario]
    ordem = (
        por_uf[por_uf["janela"] == potencial.JANELAS[-1]]
        .sort_values("delta_mediano")["uf"]
        .tolist()
    )
    faixa = go.Figure()
    for janela, cor, deslocamento in zip(
        potencial.JANELAS, ["#86b6ef", "#184f95"], [-0.18, 0.18]
    ):
        parte = por_uf[por_uf["janela"] == janela].set_index("uf").loc[ordem]
        posicoes = [i + deslocamento for i in range(len(ordem))]
        faixa.add_trace(
            go.Scatter(
                x=parte["delta_mediano"] * 100,
                y=posicoes,
                mode="markers",
                name=janela,
                marker={
                    "size": 9,
                    "color": cor,
                    "line": {"width": 2, "color": "#ffffff"},
                },
                error_x={
                    "type": "data",
                    "symmetric": False,
                    "array": (parte["delta_max"] - parte["delta_mediano"]) * 100,
                    "arrayminus": (parte["delta_mediano"] - parte["delta_min"]) * 100,
                    "color": cor,
                    "thickness": 2,
                    "width": 0,
                },
                customdata=list(
                    zip(
                        parte.index,
                        parte["delta_min"] * 100,
                        parte["delta_max"] * 100,
                    )
                ),
                hovertemplate=(
                    "%{customdata[0]} · " + janela + "<br>mediana %{x:.1f}%"
                    "<br>faixa %{customdata[1]:.1f}% a %{customdata[2]:.1f}%<extra></extra>"
                ),
            )
        )
    faixa.add_vline(x=0, line_color="#8a8f98", line_width=1)
    faixa.update_layout(
        height=760,
        margin={"l": 10, "r": 10, "t": 30, "b": 40},
        xaxis={
            "title": "Variação da irradiação (%)",
            "ticksuffix": "%",
            "zeroline": False,
        },
        yaxis={
            "tickmode": "array",
            "tickvals": list(range(len(ordem))),
            "ticktext": [f"<b>{s}</b>" if s == uf else s for s in ordem],
        },
        legend={"orientation": "h", "y": 1.03, "x": 0},
    )
    st.plotly_chart(faixa, width="stretch")
    cruzam = int(((por_uf["delta_min"] < 0) & (por_uf["delta_max"] > 0)).sum())
    st.caption(
        "Ponto: mediana dos 5 modelos; traço: faixa entre o menor e o maior. "
        f"Em {cruzam} das {len(por_uf)} combinações UF x janela, a faixa cruza o zero: "
        "os modelos não concordam nem no sinal. A conclusão robusta é a ordem de grandeza "
        "(poucos por cento), não o sinal de cada UF."
    )
    st.download_button(
        "Baixar cenários por UF (CSV)",
        para_csv(dados.cenarios_uf(base, visao, None)),
        file_name=f"cenarios_uf_{visao}.csv",
        mime="text/csv",
    )

# ═══════════════════ Metodologia ═══════════════════

with aba_metodologia:
    premissas = potencial.PREMISSAS
    st.markdown(
        f"""
**Potencial técnico (x).** Geração possível nos telhados residenciais:
domicílios x **{fmt(premissas["area_util_telhado_m2"])} m² úteis** por domicílio x
**eficiência do painel de {fmt(premissas["eficiencia_painel"] * 100)}%** x irradiação
(NASA POWER, média 2023–2025) x **PR (performance ratio) de {fmt(premissas["performance_ratio"], 2)}**
x 365 dias. A área de telhado é a premissa mais incerta: a Gold traz a sensibilidade com
10 e 20 m² (±33% em x).

**Produção estimada (y).** Potência da micro e minigeração Residencial e Rural com geração
na própria unidade consumidora (base ANEEL {premissas["base_aneel"]}), convertida em energia
com a mesma irradiação e o mesmo PR. **Gap** = x − y; **% realizado** = y / x.

**Visões.** A visão corrigida (padrão) imputa a potência dos registros de 75 kW da
COPEL-DIS e conta como solares os 156 registros sem fonte; o critério ANEEL usa o dado
oficial; o limite conservador corrige só os residenciais. Detalhes na
[atualização da base 10/2026]({link_doc("docs/potencial/atualizacao_base_10_2026.md")}).

**Fatores (SHAP).** Um modelo LightGBM, validado com as UFs separadas entre treino e teste,
prevê a taxa de realização a partir de renda, urbanização, economia agropecuária, tarifa,
distribuidora, ICMS, irradiação, população e densidade. O SHAP mostra quanto cada fator
empurra a previsão para cima ou para baixo em relação à média. **É associação, não
causalidade:** não diz o que aconteceria se o fator mudasse. O poder explicativo é
moderado (R² fora da amostra de cerca de 0,30).

**Cenários 2030–2050.** Variação da irradiação de 5 modelos do NEX-GDDP-CMIP6 (método
delta sobre a NASA POWER), com a potência instalada fixa. Cenário com faixa de incerteza,
não previsão.

Metodologia completa, validação e limitações: [docs/potencial/README.md]({link_doc("docs/potencial/README.md")}).
"""
    )

rodape()
