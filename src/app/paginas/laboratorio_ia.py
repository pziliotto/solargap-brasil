"""
PROJETO: SolarGap Brasil
ARQUIVO: paginas/laboratorio_ia.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 16/11/2026

DESCRIÇÃO:
    Interface para os modelos de linguagem locais (TP4), via API:
        1. Status dos modelos — GET /ia/status;
        2. Processar um texto — POST /processar_texto (texto colado ou uma
           notícia do corpus como exemplo);
        3. Como os modelos foram escolhidos — resumo do benchmark.

POR QUE VIA API E NÃO CARREGANDO O MODELO AQUI:
    Os modelos ocupam ~1,5 GB de memória e levam segundos para carregar. Ficam
    em um único processo (a API), compartilhados por todos os clientes — o
    painel, o Swagger e, no TP5, o agente. O painel continua leve e funciona
    mesmo numa máquina sem PyTorch.

ERROS EXIBIDOS (vindos da API):
    503  modelos carregando ou com falha de carga
    504  inferência acima do tempo limite
    422  texto inválido (curto demais, longo demais)

PRÉ-REQUISITO:
    API rodando em outro terminal, a partir da raiz:
        uvicorn src.api.main:app
"""

import pandas as pd
import streamlit as st

from src.app import carregamento as dados
from src.app import cliente_api
from src.app.componentes import rodape
from src.servicos.texto import texto_para_modelo

NOMES_TAREFAS = {
    "resumo": "Resumo",
    "relevancia": "Relevância (trata de energia solar?)",
    "tom": "Tom — experimental",
}
ROTULOS_TOM = {
    "favoravel": "Favorável",
    "desfavoravel": "Desfavorável",
    "neutro": "Neutro",
}
ESTADOS = {
    "pronto": ("✅", "pronto"),
    "carregando": ("⏳", "carregando"),
    "nao_carregado": ("⚪", "não carregado"),
    "falhou": ("❌", "falhou"),
}

st.title("🧠 Laboratório de IA")
st.markdown(
    "Modelos de linguagem **executados localmente** (HuggingFace Transformers), sem enviar "
    "texto a serviços externos. Cole uma notícia ou escolha uma do corpus."
)

# ═══════════════════ 1. Status ═══════════════════

status = cliente_api.status_ia()
if not status.ok:
    if status.status is None:
        st.error(status.erro, icon="🔌")
        st.code("uvicorn src.api.main:app", language="bash")
        st.caption(
            "Na primeira execução a API baixa os modelos (~2 GB) para o cache do HuggingFace."
        )
    else:
        st.error(
            f"Não foi possível consultar os modelos (HTTP {status.status}): {status.erro}"
        )
    rodape()
    st.stop()

info = status.dados
colunas = st.columns(len(info["tarefas"]) + 1)
colunas[0].metric(
    "Dispositivo",
    (info["dispositivo"] or "—").upper(),
    help="CUDA = GPU NVIDIA; CPU = sem GPU.",
)
for coluna, tarefa in zip(colunas[1:], info["tarefas"]):
    icone, rotulo = ESTADOS[tarefa["estado"]]
    coluna.metric(
        NOMES_TAREFAS[tarefa["tarefa"]].split(" (")[0],
        f"{icone} {rotulo}",
        help=f"{tarefa['modelo']}" + (f" — {tarefa['erro']}" if tarefa["erro"] else ""),
    )

if any(t["estado"] == "carregando" for t in info["tarefas"]):
    st.info(
        "Os modelos estão carregando. Aguarde alguns segundos e atualize.", icon="⏳"
    )
    if st.button("Atualizar status"):
        st.rerun()
for tarefa in info["tarefas"]:
    if tarefa["estado"] == "falhou":
        st.error(f"Falha ao carregar o modelo de {tarefa['tarefa']}: {tarefa['erro']}")

st.divider()

# ═══════════════════ 2. Processar ═══════════════════

st.subheader("Processar um texto")

corpus = dados.carregar_corpus()
if "texto_lab" not in st.session_state:
    st.session_state["texto_lab"] = ""


def _usar_exemplo() -> None:
    linha = corpus.set_index("id").loc[st.session_state["exemplo_lab"]]
    st.session_state["texto_lab"] = texto_para_modelo(
        linha["titulo"], linha["linha_fina"], linha["texto"], linha["nivel_texto"]
    )


if not corpus.empty:
    c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
    c1.selectbox(
        "Exemplo do corpus",
        corpus["id"],
        format_func=lambda i: corpus.set_index("id").loc[i, "titulo"],
        key="exemplo_lab",
    )
    c2.button("Usar exemplo", on_click=_usar_exemplo, width="stretch")

texto = st.text_area(
    "Texto da notícia",
    key="texto_lab",
    height=220,
    max_chars=20_000,
    placeholder="Cole aqui uma notícia em português (mínimo de 8 palavras).",
)
palavras = len(texto.split())
st.caption(
    f"{palavras} palavras."
    + (
        " Acima de ~350 palavras, os modelos leem só o início do texto."
        if palavras > 350
        else ""
    )
)

tarefas = st.pills(
    "Tarefas",
    list(NOMES_TAREFAS),
    default=["resumo", "relevancia"],
    format_func=NOMES_TAREFAS.get,
    selection_mode="multi",
    key="tarefas_lab",
)

if st.button("Processar", type="primary", disabled=not texto.strip() or not tarefas):
    with st.spinner("Processando com os modelos locais..."):
        resposta = cliente_api.processar_texto(texto, list(tarefas))
    st.session_state["resultado_lab"] = resposta

resposta = st.session_state.get("resultado_lab")
if resposta is not None:
    if not resposta.ok:
        mensagens = {
            503: ("Modelo indisponível", "⏳"),
            504: ("Tempo esgotado", "⌛"),
            422: ("Texto inválido", "✏️"),
        }
        titulo, icone = mensagens.get(resposta.status, ("Erro", "⚠️"))
        st.error(f"**{titulo}** — {resposta.erro}", icon=icone)
    else:
        corpo = resposta.dados
        resultados = corpo["resultados"]
        st.success(
            f"Processado em {corpo['duracao_ms'] / 1000:.1f} s ({corpo['dispositivo'].upper()}).",
            icon="✅",
        )

        if "resumo" in resultados:
            r = resultados["resumo"]
            with st.container(border=True):
                st.markdown("**Resumo**")
                st.write(r["resumo"])
                if r["truncado"]:
                    st.caption(
                        f"Texto com {r['tokens_entrada']} tokens: o modelo leu só os primeiros 512."
                    )

        if "relevancia" in resultados:
            r = resultados["relevancia"]
            with st.container(border=True):
                st.markdown("**Relevância**")
                st.metric(
                    "Trata de energia solar?",
                    "Sim" if r["relevante"] else "Não",
                    f"{r['probabilidade']:.0%} de probabilidade",
                    delta_color="off",
                )
                st.progress(r["probabilidade"])
                if r.get("por_termo_gd"):
                    st.caption(
                        "Relevante pela regra de palavra: a primeira linha cita um termo de "
                        "geração distribuída, mesmo com probabilidade abaixo de 40%."
                    )

        if "tom" in resultados:
            r = resultados["tom"]
            with st.container(border=True):
                st.markdown("**Tom — experimental**")
                st.warning(r["aviso"], icon="🧪")
                distribuicao = pd.DataFrame(
                    {
                        "Tom": [ROTULOS_TOM[k] for k in r["distribuicao"]],
                        "Probabilidade": list(r["distribuicao"].values()),
                    }
                )
                st.bar_chart(
                    distribuicao,
                    x="Tom",
                    y="Probabilidade",
                    horizontal=True,
                    height=180,
                )

        with st.expander("Resposta completa da API (JSON)"):
            st.json(corpo)

st.divider()

# ═══════════════════ 3. Escolha dos modelos ═══════════════════

st.subheader("Como os modelos foram escolhidos")
st.markdown(
    """
Cinco candidatos foram comparados no próprio corpus, numa GTX 1660 Ti (6 GB):

| Tarefa | Modelo escolhido | Resultado | Linha de base |
|---|---|---|---|
| Resumo | `recogna-nlp/ptt5-base-summ` (223 M parâmetros) | ROUGE-1 0,344 · 1,9 s por notícia | 0,309 (início do texto) |
| Relevância | `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` (279 M) | F1 macro 0,71 · 0,8 s | 0,43 (responder sempre "sim") |
| Tom | mesmo mDeBERTa | acurácia 0,43 | 0,83 (sempre "favorável") — **reprovado** |

O LLM generativo testado (Qwen2.5-1.5B) resumiu pior (ROUGE-1 0,284), levou 11 s por notícia
e ocupou 3 GB da GPU. Detalhes em `docs/escolha_modelo.md`.
"""
)
rodape()
