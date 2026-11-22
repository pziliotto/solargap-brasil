"""
PROJETO: SolarGap Brasil
ARQUIVO: componentes.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO: 22/11/2026 — TP4.5, Tarefa 7: seletor com três visões
             (corrigida, ANEEL, conservadora), desenhado em todas as páginas

DESCRIÇÃO:
    Peças reutilizadas pelas páginas do app multipáginas (TP3):
        - seletor de visão da base (todas as páginas) e filtros dos
          indicadores (métrica, período, classe; só nas páginas de análise);
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

VISOES = indicadores.ROTULOS_VISAO  # chave -> rótulo do seletor
URL_REPOSITORIO = "https://github.com/pziliotto/solargap-brasil/blob/main/"


def link_doc(caminho: str) -> str:
    """Link para um documento do repositório (ex.: docs/potencial/README.md)."""
    return URL_REPOSITORIO + caminho


DOC_ATUALIZACAO_BASE = link_doc("docs/potencial/atualizacao_base_10_2026.md")
AJUDA_VISAO = (
    "A base é a da ANEEL de 10/2026 (2026 parcial, até outubro). As visões diferem em "
    "duas correções de preenchimento.\n\n"
    "**75 kW da COPEL-DIS.** A distribuidora do Paraná registra 75 kW, o teto da "
    "microgeração, em cerca de 47 mil sistemas, inclusive residências. A **visão "
    "corrigida** (padrão) atribui a esses registros a potência mediana de sistemas "
    "semelhantes do mesmo município. O **limite conservador** corrige só os "
    "residenciais (cerca de 28 mil) e mantém os 75 kW de comércios, propriedades "
    "rurais e indústrias, que podem de fato ter essa potência.\n\n"
    "**Registros sem fonte (MA).** Na base de 08/2026, 44% dos registros do MA vinham "
    "sem fonte de geração e o projeto os contava como solares. Na base de 10/2026, a "
    "ANEEL retirou esses registros e o MA não depende mais da visão. Restam 156 "
    "registros sem fonte no país (PE, SC, MG e outros), contados como solares na "
    "corrigida e na conservadora.\n\n"
    "O **critério ANEEL** usa o dado oficial sem correções, como o painel da agência.\n\n"
    f"Detalhes: [atualização da base 10/2026]({DOC_ATUALIZACAO_BASE})."
)
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
    visao: str  # chave: corrigida | aneel | conservadora
    metrica: str
    ano_inicio: int
    ano_fim: int
    classes: tuple[str, ...]

    @property
    def info_metrica(self) -> indicadores.Metrica:
        return indicadores.METRICAS[self.metrica]

    @property
    def rotulo_visao(self) -> str:
        return VISOES[self.visao]

    @property
    def incluir_imputados(self) -> bool:
        return self.visao != "aneel"


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


def seletor_visao() -> str:
    """Seletor de visão da base, desenhado pelo app.py em todas as páginas.

    Devolve a chave (corrigida | aneel | conservadora) e a grava em
    st.session_state["visao_base"], lida pelas páginas com visao_atual().
    """
    with st.sidebar:
        visao = widget_persistente(
            st.radio,
            "Visão dos dados",
            "visao",
            indicadores.VISAO_PADRAO,
            options=list(VISOES),
            format_func=VISOES.get,
            help=AJUDA_VISAO,
        )
    st.session_state["visao_base"] = visao
    return visao


def visao_atual() -> str:
    """Visão escolhida na barra lateral (padrão: corrigida)."""
    return st.session_state.get("visao_base", indicadores.VISAO_PADRAO)


def barra_lateral_filtros(agregado: pd.DataFrame, visao: str) -> FiltrosPainel:
    ano_min, ano_max = indicadores.anos_disponiveis(agregado)
    classes_todas = indicadores.classes_disponiveis(agregado)

    with st.sidebar:
        st.header("Filtros")
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
            st.caption(f"⚠️ {esquema.ANO_PARCIAL} é parcial: dados até outubro.")

    return FiltrosPainel(
        visao=visao,
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


def aviso_imputados(
    indicadores_uf: pd.DataFrame,
    visao: str,
    potencia: dict[str, float] | None = None,
) -> None:
    """Explica as correções da visão escolhida e como voltar ao dado oficial.

    potencia: saída de indicadores.potencia_suspeita para o mesmo recorte e visão.
    """
    if visao == "aneel":
        return
    partes = []
    if potencia and potencia["registros"]:
        alcance = (
            "dos residenciais entre os"
            if visao == "conservadora"
            else "de"
        )
        partes.append(
            f"corrige a potência {alcance} {fmt(potencia['registros'])} sistemas registrados "
            f"com 75 kW, o teto da microgeração ({fmt(potencia['kw_oficial'] / 1_000, 1)} MW "
            f"no dado oficial, {fmt(potencia['kw_corrigido'] / 1_000, 1)} MW após a "
            "imputação)"
        )
    imputados = int(indicadores_uf["qtd_imputados"].sum())
    if imputados:
        partes.append(f"conta como solares {fmt(imputados)} registros sem fonte informada")
    if partes:
        st.info(
            f"Esta visão {' e '.join(partes)}. Alterne para **Critério ANEEL** na barra "
            "lateral para reproduzir os números do painel oficial.",
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
