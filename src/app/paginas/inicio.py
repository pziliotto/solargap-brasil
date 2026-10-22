"""
PROJETO: SolarGap Brasil
ARQUIVO: paginas/inicio.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Página inicial: problema de negócio, objetivo, números-chave do Brasil e
    um guia das demais páginas. Substitui o expander "Sobre o projeto" do TP2.

OBS.:
    Os números-chave usam a visão padrão (com correção de preenchimento e
    período completo), e não os filtros da barra lateral — a página inicial é
    o retrato geral, igual para todo visitante.
"""

import streamlit as st

from src.app import carregamento as dados
from src.app.componentes import fmt, rodape
from src.preparacao import esquema
from src.servicos import indicadores

agregado = dados.carregar_agregado()
dim_uf = dados.carregar_uf()
corpus = dados.carregar_corpus()

ano_min, ano_max = indicadores.anos_disponiveis(agregado)
classes = tuple(indicadores.classes_disponiveis(agregado))
indicadores_uf = dados.indicadores_por_uf(
    agregado, dim_uf, ano_min, ano_max, classes, True
)
referencia = indicadores.media_brasil(indicadores_uf)
abaixo_media = int(
    (indicadores_uf["watts_por_habitante"] < referencia["watts_por_habitante"]).sum()
)

st.title(":green[SolarGap - Brasil]")
st.caption("Onde está o próximo mercado solar?")

st.markdown(
    """
<p style='text-align: justify; font-size: 1.05rem; line-height: 1.6;'>
Desde a promulgação da Lei 14.300/2022 (Marco Legal da Geração Distribuída), a geração
distribuída de energia solar cresceu de forma acentuada no Brasil. Esse crescimento, porém,
não se distribui de forma equânime entre os estados — o que pode aprofundar desigualdades
regionais de acesso à transição energética. O SolarGap Brasil mapeia e quantifica essa
disparidade com dados públicos da ANEEL e do IBGE, identificando quem lidera, quem fica para
trás e onde estão as oportunidades ainda não exploradas pelo mercado solar.
</p>
""",
    unsafe_allow_html=True,
)

st.subheader(f"O Brasil solar distribuído, até ago/{esquema.ANO_PARCIAL}")
k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "Potência instalada", f"{fmt(indicadores_uf['potencia_mw'].sum() / 1000, 1)} GW"
)
k2.metric("Empreendimentos", fmt(indicadores_uf["qtd_empreendimentos"].sum()))
k3.metric("Média nacional", f"{fmt(referencia['watts_por_habitante'], 1)} W/hab")
k4.metric(
    "UFs abaixo da média",
    f"{abaixo_media} de {esquema.TOTAL_UFS}",
    help="UFs com watts por habitante abaixo da média nacional (total do país / população).",
)

st.subheader("Como navegar")
c1, c2 = st.columns(2)
with c1:
    st.page_link(
        "paginas/panorama.py", label="**Panorama** — ranking das 27 UFs", icon="📊"
    )
    st.page_link(
        "paginas/evolucao.py",
        label="**Evolução e crescimento** — séries e taxa de crescimento",
        icon="📈",
    )
    st.page_link(
        "paginas/oportunidades.py",
        label="**Oportunidades** — adoção x crescimento e política de ICMS",
        icon="🎯",
    )
with c2:
    st.page_link(
        "paginas/noticias.py",
        label=f"**Notícias** — corpus de {len(corpus)} notícias e nuvem de palavras",
        icon="📰",
    )
    st.page_link(
        "paginas/dados.py",
        label="**Dados** — downloads e comparação com seu indicador",
        icon="📁",
    )
    st.page_link(
        "paginas/api.py",
        label="**API** — status, consultas e envio de notícias",
        icon="🔌",
    )

with st.expander("Indicadores e alinhamento ESG"):
    st.markdown(
        """
| Indicador | O que mede |
|---|---|
| Watts por habitante | Potência solar instalada dividida pela população (Censo 2022) |
| Empreendimentos por 100 mil hab. | Difusão: quantos sistemas existem para cada 100 mil pessoas |
| Ranking de disparidade | Posição das 27 UFs, com a média nacional como referência |
| Taxa de crescimento | Variação anual do parque instalado e crescimento médio desde a Lei 14.300 |

**ODS 7** (Energia Limpa e Acessível) — metas 7.2 e 7.b · **ODS 10** (Redução das
Desigualdades) — meta 10.2.
"""
    )

rodape()
