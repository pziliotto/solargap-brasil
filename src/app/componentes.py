"""
PROJETO: SolarGap Brasil
ARQUIVO: componentes.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Peças reutilizadas pelas páginas do app multipáginas (TP3):
        - filtros globais da barra lateral (visão, métrica, período, classe);
        - formatação de números no padrão brasileiro e exportação CSV;
        - avisos padronizados (ano parcial, registros imputados) e rodapé.

ESTADO DE SESSÃO ENTRE PÁGINAS:
    No app multipáginas (st.navigation), um widget que deixa de ser desenhado
    em uma execução tem o seu valor apagado pelo Streamlit. Como os filtros só
    aparecem nas páginas de análise, ir para "Notícias" e voltar zeraria tudo.

    Solução documentada pelo Streamlit: guardar uma cópia do valor em outra
    chave (prefixo "_"), atualizada no on_change do widget, e restaurá-la na
    chave do widget antes de desenhá-lo:

        _restaurar("metrica", padrao)          # _metrica -> metrica
        st.selectbox(..., key="metrica", on_change=_guardar, args=("metrica",))

    O widget nunca recebe default/index/value: o valor vem só do session_state.
    Passar os dois gera aviso do Streamlit e comportamento ambíguo.

COMO AS PÁGINAS RECEBEM OS FILTROS:
    O arquivo de entrada (app.py) desenha a barra lateral e grava um objeto
    FiltrosPainel em st.session_state["filtros"]. As páginas leem com
    filtros_atuais(). Assim nenhuma página repete a lógica dos filtros.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from src.preparacao import esquema
from src.servicos import indicadores

VISOES = {"Com correção de preenchimento": True, "Critério ANEEL": False}
SIGLAS = sorted(esquema.UFS)
COR_DESTAQUE = "#F4A300"
COR_BASE = "#B8C2CC"

CORES_QUADRANTE = {
    "Líder em expansão": "#2E7D32",
    "Mercado maduro": "#1565C0",
    "Mercado emergente": "#F4A300",
    "Lacuna persistente": "#C62828",
}


@dataclass(frozen=True)
class FiltrosPainel:
    visao: str
    incluir_imputados: bool
    metrica: str
    ano_inicio: int
    ano_fim: int
    classes: tuple[str, ...]

    @property
    def info_metrica(self) -> indicadores.Metrica:
        return indicadores.METRICAS[self.metrica]


# ═══════════════════ Persistência de widgets ═══════════════════


def _guardar(chave: str) -> None:
    st.session_state[f"_{chave}"] = st.session_state[chave]


def _restaurar(chave: str, padrao) -> None:
    if f"_{chave}" not in st.session_state:
        st.session_state[f"_{chave}"] = padrao
    st.session_state[chave] = st.session_state[f"_{chave}"]


def widget_persistente(funcao, rotulo: str, chave: str, padrao, **kwargs):
    """Desenha um widget cujo valor sobrevive à troca de página."""
    _restaurar(chave, padrao)
    return funcao(rotulo, key=chave, on_change=_guardar, args=(chave,), **kwargs)


# ═══════════════════ Filtros globais ═══════════════════


def barra_lateral_filtros(agregado: pd.DataFrame) -> FiltrosPainel:
    ano_min, ano_max = indicadores.anos_disponiveis(agregado)
    classes_todas = indicadores.classes_disponiveis(agregado)

    with st.sidebar:
        st.header("Filtros")
        visao = widget_persistente(
            st.radio,
            "Visão dos dados",
            "visao",
            list(VISOES)[0],
            options=list(VISOES),
            help=(
                "Uma distribuidora do Maranhão não informa a fonte de geração em cerca de "
                "73 mil registros. 'Com correção' os conta como solares (99,98% dos registros "
                "com fonte conhecida são solares); 'Critério ANEEL' os exclui, como o painel oficial."
            ),
        )
        metrica = widget_persistente(
            st.selectbox,
            "Métrica",
            "metrica",
            "watts_por_habitante",
            options=list(indicadores.METRICAS),
            format_func=lambda chave: indicadores.METRICAS[chave].rotulo,
        )
        ano_inicio, ano_fim = widget_persistente(
            st.slider,
            "Ano de conexão",
            "periodo",
            (ano_min, ano_max),
            min_value=ano_min,
            max_value=ano_max,
        )
        classes = widget_persistente(
            st.multiselect,
            "Classe de consumo",
            "classes",
            classes_todas,
            options=classes_todas,
        )
        if ano_fim >= esquema.ANO_PARCIAL:
            st.caption(f"⚠️ {esquema.ANO_PARCIAL} é parcial: dados até agosto.")

    return FiltrosPainel(
        visao=visao,
        incluir_imputados=VISOES[visao],
        metrica=metrica,
        ano_inicio=int(ano_inicio),
        ano_fim=int(ano_fim),
        classes=tuple(classes),
    )


def filtros_atuais() -> FiltrosPainel:
    """Filtros gravados pelo app.py nesta execução. Interrompe se não houver classe."""
    filtros: FiltrosPainel | None = st.session_state.get("filtros")
    if filtros is None:
        st.error("Filtros indisponíveis. Abra o app pelo arquivo src/app/app.py.")
        st.stop()
    if not filtros.classes:
        st.warning("Selecione ao menos uma classe de consumo na barra lateral.")
        st.stop()
    return filtros


def uf_em_destaque(rotulo: str = "Destacar uma UF") -> str:
    """Seletor de UF compartilhado por Panorama e Evolução (persistente)."""
    return widget_persistente(
        st.selectbox, rotulo, "uf_destaque", "Nenhuma", options=["Nenhuma"] + SIGLAS
    )


# ═══════════════════ Formatação ═══════════════════


def fmt(valor: float, casas: int = 0) -> str:
    """Formato brasileiro: 1234567.8 -> 1.234.567,8"""
    if valor is None or pd.isna(valor):
        return "—"
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def para_csv(df: pd.DataFrame) -> bytes:
    # utf-8-sig: o Excel no Windows reconhece a acentuação
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")


# ═══════════════════ Avisos ═══════════════════


def aviso_imputados(indicadores_uf: pd.DataFrame, incluir_imputados: bool) -> None:
    imputados = int(indicadores_uf["qtd_imputados"].sum())
    if incluir_imputados and imputados:
        st.info(
            f"Esta visão inclui {fmt(imputados)} registros sem fonte informada "
            "(quase todos no Maranhão), contados como solares. Alterne para **Critério ANEEL** "
            "na barra lateral para reproduzir os números do painel oficial.",
            icon="ℹ️",
        )


def faixa_ano_parcial(figura, ano_fim: int) -> None:
    """Sombreia o ano parcial em gráficos com eixo x de anos."""
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


def rodape() -> None:
    st.divider()
    st.caption(
        "Fontes: ANEEL — Relação de Empreendimentos de MMGD (ODbL) · IBGE — Censo 2022 · "
        "Agência Brasil e Agência Gov (EBC) · CONFAZ — Convênio ICMS 16/15. "
        "Metodologia e decisões de tratamento no Data Summary Report."
    )
