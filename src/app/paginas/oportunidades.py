"""
PROJETO: SolarGap Brasil
ARQUIVO: paginas/oportunidades.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Página nova do TP3, a que responde diretamente à pergunta do projeto —
    "onde está o próximo mercado solar?":
        1. Matriz de oportunidade: adoção per capita (estoque até ago/2026) x
           crescimento médio do parque (CAGR) — quatro quadrantes;
        2. Política pública: início da isenção de ICMS (Convênio ICMS 16/15,
           coletado do CONFAZ) cruzado com a adoção.

LEITURA DOS QUADRANTES (referência = Brasil):
    Líder em expansão   adoção alta, crescimento alto
    Mercado maduro      adoção alta, crescimento baixo
    Mercado emergente   adoção baixa, crescimento alto  -> oportunidade de mercado
    Lacuna persistente  adoção baixa, crescimento baixo -> foco de política (ODS 10)

FILTROS:
    Usa visão (imputados) e classe de consumo da barra lateral. O período NÃO se
    aplica: a adoção é o estoque acumulado e o crescimento tem janela própria.
"""

import plotly.express as px
import streamlit as st

from src.app import carregamento as dados
from src.app.componentes import CORES_QUADRANTE, filtros_atuais, fmt, rodape
from src.preparacao import esquema
from src.servicos import indicadores

filtros = filtros_atuais()
agregado = dados.carregar_agregado()
ano_min, ano_max = indicadores.anos_disponiveis(agregado)
estoque = dados.indicadores_por_uf(
    agregado,
    dados.carregar_uf(),
    ano_min,
    ano_max,
    filtros.classes,
    filtros.incluir_imputados,
)

st.title("🎯 Oportunidades")
st.caption(
    f"Adoção acumulada até ago/{esquema.ANO_PARCIAL} x crescimento do parque instalado · "
    f"visão: {filtros.visao}. O filtro de período não se aplica a esta página."
)

anos_completos = list(range(esquema.ANO_MINIMO, esquema.ANO_PARCIAL))
c1, c2 = st.columns(2)
ano_base = c1.selectbox(
    "Crescimento a partir de",
    anos_completos[:-1],
    index=anos_completos.index(indicadores.ANO_BASE_CRESCIMENTO),
    key="ano_base_oportunidade",
)
finais = [a for a in anos_completos if a > ano_base]
ano_final = c2.selectbox(
    "até", finais, index=len(finais) - 1, key="ano_final_oportunidade"
)

crescimento, cagr_brasil = dados.taxa_crescimento(
    agregado, filtros.classes, filtros.incluir_imputados, ano_base, ano_final
)
matriz, referencia = indicadores.matriz_oportunidade(estoque, crescimento, cagr_brasil)

# ═══════════════════ 1. Matriz de oportunidade ═══════════════════

st.subheader("Matriz de oportunidade")
figura = px.scatter(
    matriz,
    x="watts_por_habitante",
    y="cagr_pct",
    size="potencia_mw",
    color="quadrante",
    color_discrete_map=CORES_QUADRANTE,
    text="sigla_uf",
    size_max=45,
    hover_data={"nome_uf": True, "potencia_mw": ":.0f", "quadrante": False},
    labels={
        "watts_por_habitante": "Adoção (W por habitante)",
        "cagr_pct": f"Crescimento médio {ano_base}-{ano_final} (% ao ano)",
        "potencia_mw": "Potência (MW)",
        "nome_uf": "Estado",
        "quadrante": "Quadrante",
    },
)
figura.add_vline(
    x=referencia["watts_por_habitante"], line_dash="dash", line_color="gray"
)
figura.add_hline(y=referencia["cagr_pct"], line_dash="dash", line_color="gray")
figura.update_traces(textposition="top center")
figura.update_layout(height=560, margin=dict(t=30, b=10), legend_title=None)
st.plotly_chart(figura, width="stretch")
st.caption(
    f"Linhas tracejadas: referência nacional — {fmt(referencia['watts_por_habitante'], 1)} W/hab e "
    f"{fmt(referencia['cagr_pct'], 1)}% ao ano. Tamanho do círculo: potência instalada. "
    "UFs com parque pequeno no ano base tendem a exibir taxas altas."
)

colunas = st.columns(4)
for coluna, quadrante in zip(colunas, CORES_QUADRANTE, strict=True):
    grupo = matriz[matriz["quadrante"] == quadrante]
    with coluna:
        st.markdown(f"**{quadrante}** ({len(grupo)})")
        st.caption(indicadores.DESCRICAO_QUADRANTES[quadrante])
        for _, linha in grupo.iterrows():
            st.markdown(
                f"- {linha['nome_uf']} — {fmt(linha['watts_por_habitante'], 0)} W/hab, "
                f"{fmt(linha['cagr_pct'], 1)}% a.a."
            )

emergentes = matriz[matriz["quadrante"] == "Mercado emergente"]
if not emergentes.empty:
    st.success(
        f"**Onde está o próximo mercado solar?** {len(emergentes)} UFs têm adoção abaixo da "
        f"média nacional, mas crescem acima dela: "
        f"{', '.join(emergentes['nome_uf'])}.",
        icon="☀️",
    )

# ═══════════════════ 2. Política pública: ICMS ═══════════════════

st.divider()
st.subheader("Isenção de ICMS e adoção")
icms = dados.carregar_icms()

if icms is None:
    st.info(
        "A tabela de adesão ao Convênio ICMS 16/15 ainda não foi gerada. Rode, na raiz do projeto: "
        "`python -m src.data_acquisition.icms_confaz`",
        icon="ℹ️",
    )
else:
    st.markdown(
        "O **Convênio ICMS 16/15** (CONFAZ) autoriza os estados a isentar de ICMS a energia "
        "compensada na geração distribuída. Hoje todas as 27 UFs aderiram, mas em datas "
        "diferentes — de 2015 a 2018. A pergunta: quem aderiu antes adotou mais?"
    )
    base = matriz.merge(icms, on="sigla_uf", how="left", suffixes=("", "_icms"))
    rho = indicadores.correlacao_spearman(
        base["meses_desde_inicio"], base["watts_por_habitante"]
    )

    figura = px.scatter(
        base,
        x="inicio_efeitos",
        y="watts_por_habitante",
        color="quadrante",
        color_discrete_map=CORES_QUADRANTE,
        text="sigla_uf",
        hover_data={"nome_uf": True, "convenio_adesao": True, "quadrante": False},
        labels={
            "inicio_efeitos": "Início da isenção de ICMS",
            "watts_por_habitante": "Adoção (W por habitante)",
            "convenio_adesao": "Convênio",
            "nome_uf": "Estado",
        },
    )
    figura.add_hline(
        y=referencia["watts_por_habitante"], line_dash="dash", line_color="gray"
    )
    figura.update_traces(textposition="top center", marker_size=12)
    figura.update_layout(height=460, margin=dict(t=30, b=10), legend_title=None)
    st.plotly_chart(figura, width="stretch")

    ref = referencia["watts_por_habitante"]
    pioneiras_abaixo = base[
        (base["ano_inicio_efeitos"] == 2015) & (base["watts_por_habitante"] < ref)
    ]
    tardias_acima = base[
        (base["ano_inicio_efeitos"] >= 2017) & (base["watts_por_habitante"] >= ref)
    ]
    texto_rho = "indisponível" if rho is None else fmt(rho, 2)
    st.markdown(
        f"Correlação de Spearman entre o tempo de isenção e a adoção per capita: **{texto_rho}**. "
        f"Entre as UFs com isenção desde 2015, {len(pioneiras_abaixo)} estão abaixo da média "
        f"nacional ({', '.join(pioneiras_abaixo['sigla_uf'])}); entre as que aderiram de 2017 em "
        f"diante, {len(tardias_acima)} estão acima ({', '.join(tardias_acima['sigla_uf']) or 'nenhuma'})."
    )
    st.caption(
        "Correlação não é causalidade, e a amostra tem só 27 UFs. A isenção de ICMS é condição "
        "favorável, mas não explica sozinha a disparidade: irradiação, renda, tarifa da "
        "distribuidora e acesso a crédito também pesam."
    )
    st.dataframe(
        base[
            [
                "sigla_uf",
                "nome_uf",
                "convenio_adesao",
                "inicio_efeitos",
                "forma_inclusao",
                "observacao",
            ]
        ].sort_values("inicio_efeitos"),
        column_config={
            "sigla_uf": "UF",
            "nome_uf": "Estado",
            "convenio_adesao": "Convênio",
            "inicio_efeitos": st.column_config.DateColumn(
                "Início da isenção", format="DD/MM/YYYY"
            ),
            "forma_inclusao": "Forma de inclusão",
            "observacao": st.column_config.TextColumn("Observação", width="large"),
        },
        hide_index=True,
        width="stretch",
    )

rodape()
