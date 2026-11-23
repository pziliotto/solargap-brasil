"""
PROJETO: SolarGap Brasil
ARQUIVO: paginas/agente.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026 (TP5)

DESCRIÇÃO:
    Página "Agente de decisão": conversa com o agente inteligente do TP5
    (src/agente). O gestor ou investidor pergunta em português e recebe
    diagnóstico, fatores e recomendações, com gráfico dos dados usados e a
    trilha de cada número (ferramentas, fatos e verificação).

POR QUE O AGENTE RODA AQUI E NÃO VIA API:
    Diferente do Laboratório de IA (modelos de 1,5 GB dentro da API), o
    agente é leve: lê a Gold e conversa com o LLM, que fica num processo à
    parte (Ollama). Rodando no próprio painel, a página funciona sem a API no
    ar. A API expõe o mesmo agente em POST /agente/perguntar.

MEMÓRIA:
    A conversa fica em st.session_state: histórico (perguntas e respostas) e
    contexto (último recorte), enviados ao agente a cada pergunta.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from src.agente.agente import Agente
from src.app.componentes import rodape, visao_atual
from src.servicos.dados import DadosIndisponiveis

EXEMPLOS = [
    "Onde investir em geração distribuída no Rio Grande do Sul?",
    "Por que Caxias do Sul está abaixo do esperado e o que fazer?",
    "Compare RS e SC",
    "Como fica o potencial de Recife nos cenários climáticos até 2050?",
]
ROTULO_MODO = {
    "llm": "🧠 Modelo de linguagem",
    "regras": "⚙️ Modo por regras (sem LLM)",
    "misto": "🧠⚙️ Misto (o LLM falhou na redação)",
}
COR_ELEVA, COR_REDUZ = "#256abf", "#c62828"


@st.cache_resource(show_spinner="Preparando o agente...")
def carregar_agente() -> Agente:
    return Agente.carregar()


def _estado() -> dict:
    if "agente_conversa" not in st.session_state:
        st.session_state["agente_conversa"] = {"trocas": [], "contexto": {}}
    return st.session_state["agente_conversa"]


def _grafico(resposta: dict, chave: str) -> None:
    """Visualização dos dados que sustentam a resposta."""
    por_nome = {f["nome"]: f for f in resposta["ferramentas"] if not f["erro"]}
    if "oportunidades" in por_nome and por_nome["oportunidades"]["dados"]:
        tabela = pd.DataFrame(por_nome["oportunidades"]["dados"])
        tabela["municipio"] = tabela["nome"] + " (" + tabela["uf"] + ")"
        tabela["GWh/ano"] = tabela["gap_acima_esperado_mwh_ano"] / 1e3
        figura = px.bar(
            tabela.iloc[::-1], x="GWh/ano", y="municipio", orientation="h",
            title="Gap acima do esperado pelo perfil (onde priorizar)",
            color_discrete_sequence=[COR_ELEVA],
            hover_data={"taxa_realizacao": ":.1%", "taxa_prevista": ":.1%"},
        )  # fmt: skip
        figura.update_layout(height=300, yaxis_title=None, margin={"t": 40, "b": 10})
        st.plotly_chart(figura, width="stretch", key=f"{chave}-g1")
    explicacoes = [
        f
        for f in resposta["ferramentas"]
        if f["nome"] == "explicar_gap" and not f["erro"]
    ]
    for j, explicacao in enumerate(explicacoes[:2]):
        grupos = pd.DataFrame(explicacao["dados"]["grupos"])
        grupos = grupos[grupos["contribuicao_pp"].abs() >= 0.5]
        if grupos.empty:
            continue
        grupos = grupos.sort_values("contribuicao_pp")
        figura = px.bar(
            grupos, x="contribuicao_pp", y="rotulo", orientation="h",
            color=grupos["contribuicao_pp"] > 0,
            color_discrete_map={True: COR_ELEVA, False: COR_REDUZ},
            title=f"Fatores associados à taxa — {explicacao['dados']['nome']} (p.p., SHAP)",
        )  # fmt: skip
        figura.update_layout(
            height=280, showlegend=False, yaxis_title=None, xaxis_title="p.p. da taxa prevista",
            margin={"t": 40, "b": 10},
        )  # fmt: skip
        st.plotly_chart(figura, width="stretch", key=f"{chave}-g2-{j}")
    if "cenarios_climaticos" in por_nome:
        tabela = pd.DataFrame(por_nome["cenarios_climaticos"]["dados"])
        tabela["variação (%)"] = tabela["delta_mediano"] * 100
        tabela["erro_mais"] = (tabela["delta_max"] - tabela["delta_mediano"]) * 100
        tabela["erro_menos"] = (tabela["delta_mediano"] - tabela["delta_min"]) * 100
        figura = px.bar(
            tabela, x="janela", y="variação (%)", color="cenario", barmode="group",
            error_y="erro_mais", error_y_minus="erro_menos",
            title="Variação da irradiação (mediana e faixa entre modelos)",
            color_discrete_map={"ssp245": "#6da7ec", "ssp585": "#c62828"},
        )  # fmt: skip
        figura.update_layout(height=280, margin={"t": 40, "b": 10})
        st.plotly_chart(figura, width="stretch", key=f"{chave}-g3")


def _trilha(resposta: dict, chave: str) -> None:
    verificacao = resposta["verificacao"]
    colunas = st.columns(3)
    colunas[0].caption(
        ROTULO_MODO[resposta["modo"]]
        + (f" · {resposta['modelo']}" if resposta["modelo"] else "")
    )
    if verificacao["nao_encontrados"]:
        colunas[1].caption(
            f"⚠️ {verificacao['verificados']}/{verificacao['numeros']} números conferidos com os dados"
        )
    else:
        colunas[1].caption(
            f"✅ {verificacao['numeros']} números conferidos com os dados"
        )
    recorte = resposta["recorte"]["descricao"] + (
        " (da conversa)" if resposta["recorte_herdado"] else ""
    )
    colunas[2].caption(f"📍 {recorte} · {resposta['tempo_s']:.1f} s")
    for aviso in resposta["avisos"]:
        st.warning(aviso, icon="⚠️")
    with st.expander("Evidências: como o agente chegou a esta resposta"):
        _grafico(resposta, chave)
        st.markdown(f"**Intenção identificada:** {', '.join(resposta['intencoes'])}")
        for i, ferramenta in enumerate(resposta["ferramentas"], start=1):
            argumentos = {k: v for k, v in ferramenta["argumentos"].items() if v}
            st.markdown(f"**{i}. `{ferramenta['nome']}`** {argumentos or ''}")
            if ferramenta["erro"]:
                st.caption(f"Erro: {ferramenta['erro']}")
            for fato in ferramenta["fatos"]:
                st.markdown(f"- {fato}")
            if ferramenta["nome"] == "noticias":
                for noticia in ferramenta["dados"]:
                    st.markdown(f"  - [{noticia['titulo']}]({noticia['url']})")


def _exportar(trocas: list[dict]) -> str:
    partes = ["# Conversa com o agente SolarGap Brasil\n"]
    for troca in trocas:
        partes.append(f"## {troca['pergunta']}\n\n{troca['resposta']['resposta']}\n")
    return "\n".join(partes)


st.title("🤖 Agente de decisão")
st.markdown(
    "Pergunte sobre **onde investir**, **por que** um lugar adota pouca energia solar, "
    "**como comparar** estados ou **o que muda até 2050**. O agente identifica a UF ou o "
    "município, consulta os dados do projeto (potencial, SHAP, cenários, ICMS e notícias), "
    "escreve o diagnóstico com recomendações e **confere cada número** com os dados."
)

try:
    agente = carregar_agente()
except DadosIndisponiveis as erro:
    st.error(f"Não foi possível carregar a camada Gold: {erro}")
    st.stop()

llm_no_ar = agente.cliente.disponivel()
with st.sidebar:
    st.divider()
    st.subheader("Agente")
    if llm_no_ar:
        st.success(f"LLM no ar: {agente.cliente.config.descricao}", icon="🧠")
    else:
        st.info(
            "LLM fora do ar: o agente responde no modo por regras, com os mesmos dados. "
            f"Para ativar: `ollama pull {agente.cliente.config.modelo}` e `ollama serve`.",
            icon="⚙️",
        )
    usar_llm = st.toggle(
        "Usar modelo de linguagem", value=llm_no_ar, disabled=not llm_no_ar
    )

estado = _estado()
st.caption("Exemplos:")
colunas = st.columns(len(EXEMPLOS))
pergunta_exemplo = None
for coluna, exemplo in zip(colunas, EXEMPLOS):
    if coluna.button(exemplo, width="stretch"):
        pergunta_exemplo = exemplo

for i, troca in enumerate(estado["trocas"]):
    with st.chat_message("user"):
        st.markdown(troca["pergunta"])
    with st.chat_message("assistant"):
        st.markdown(troca["resposta"]["resposta"])
        _trilha(troca["resposta"], f"t{i}")

pergunta = (
    st.chat_input("Ex.: Onde estão as oportunidades em Santa Catarina?")
    or pergunta_exemplo
)
if pergunta:
    with st.chat_message("user"):
        st.markdown(pergunta)
    with st.chat_message("assistant"):
        with st.spinner("Consultando os dados e redigindo..."):
            historico = [
                {"pergunta": t["pergunta"], "resposta": t["resposta"]["resposta"]}
                for t in estado["trocas"][-4:]
            ]
            resposta = agente.perguntar(
                pergunta,
                historico,
                estado["contexto"],
                visao=visao_atual(),
                usar_llm=usar_llm,
            ).como_dict()
        st.markdown(resposta["resposta"])
        _trilha(resposta, f"t{len(estado['trocas'])}")
    estado["trocas"].append({"pergunta": pergunta, "resposta": resposta})
    estado["contexto"] = resposta["contexto"]

if estado["trocas"]:
    esquerda, direita = st.columns(2)
    if esquerda.button("🗑️ Limpar conversa"):
        st.session_state.pop("agente_conversa", None)
        st.rerun()
    direita.download_button(
        "⬇️ Baixar conversa (.md)", _exportar(estado["trocas"]),
        file_name="conversa_agente_solargap.md", mime="text/markdown",
    )  # fmt: skip

st.info(
    "Como ler: o agente descreve **associações** encontradas nos dados (modelo explicativo "
    "com SHAP), não efeitos causais. O potencial é técnico e residencial, com premissas fixas "
    "de telhado e eficiência. Detalhes em docs/agente/README.md.",
    icon="ℹ️",
)
rodape()
