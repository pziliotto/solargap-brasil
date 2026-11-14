"""
PROJETO: SolarGap Brasil
ARQUIVO: paginas/api.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Integração do dashboard com a API FastAPI do projeto (src/api):
        1. Status — GET /saude;
        2. Explorador de rotas — consultas GET com parâmetros, resposta em
           tabela e em JSON;
        3. Enviar notícia — POST /noticias, com as mensagens de validação
           (422) e de duplicidade (409) devolvidas pela API.

POR QUE O RESTO DO PAINEL LÊ A GOLD DIRETAMENTE:
    O painel precisa funcionar mesmo sem a API no ar (por exemplo, num deploy
    só do Streamlit). As páginas de análise leem a camada Gold pelos mesmos
    serviços que a API usa (src/servicos), então os números são idênticos.
    A API é a porta de entrada para escrita (POST) e para consumidores
    externos — entre eles, o agente inteligente do TP5.

PRÉ-REQUISITO:
    API rodando em outro terminal, a partir da raiz:
        uvicorn src.api.main:app --reload
"""

from datetime import date

import pandas as pd
import streamlit as st

from src.app import carregamento as dados
from src.app import cliente_api
from src.app.componentes import SIGLAS, rodape
from src.servicos import indicadores

st.title("🔌 API")
st.markdown(
    f"Endereço configurado: `{cliente_api.url_base()}` "
    "(altere com a variável de ambiente `SOLARGAP_API_URL`)."
)

# ═══════════════════ 1. Status ═══════════════════

status = cliente_api.saude()
if status.ok:
    saude = status.dados
    st.success(f"API no ar — versão {saude['versao']}.", icon="✅")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("UFs", saude["dados"]["ufs"])
    k2.metric(
        "Linhas do agregado", f"{saude['dados']['linhas_agregado']:,}".replace(",", ".")
    )
    k3.metric("Notícias", saude["dados"]["noticias"])
    k4.metric("Tabela de ICMS", "disponível" if saude["dados"]["icms"] else "ausente")
    st.markdown(
        f"Documentação interativa (Swagger): [{cliente_api.url_base()}/docs]({cliente_api.url_base()}/docs)"
    )
else:
    st.error(status.erro, icon="🔌")
    st.code("uvicorn src.api.main:app --reload", language="bash")

# ═══════════════════ 2. Explorador ═══════════════════

st.subheader("Explorar rotas (GET)")
ROTAS = {
    "/ranking — ranking das UFs": "/ranking",
    "/ufs/{sigla} — ficha de uma UF": "/ufs/{sigla}",
    "/series/{sigla} — série e crescimento": "/series/{sigla}",
    "/oportunidades — matriz de oportunidade": "/oportunidades",
    "/noticias — notícias filtradas": "/noticias",
    "/noticias/fontes — fontes do corpus": "/noticias/fontes",
    "/politicas/icms — adesão ao Convênio 16/15": "/politicas/icms",
}
escolha = st.selectbox("Rota", list(ROTAS), key="rota_api")
caminho = ROTAS[escolha]
parametros: dict = {}

if "{sigla}" in caminho:
    sigla = st.selectbox("UF", SIGLAS, index=SIGLAS.index("RS"), key="sigla_api")
    caminho = caminho.replace("{sigla}", sigla)
if caminho == "/ranking":
    c1, c2, c3 = st.columns(3)
    parametros["metrica"] = c1.selectbox(
        "Métrica",
        list(indicadores.METRICAS),
        format_func=lambda k: indicadores.METRICAS[k].rotulo,
        key="metrica_api",
    )
    parametros["ordem"] = c2.radio(
        "Ordem", ["desc", "asc"], horizontal=True, key="ordem_api"
    )
    parametros["limite"] = c3.number_input("Limite", 1, 27, 10, key="limite_api")
if caminho == "/noticias":
    c1, c2, c3 = st.columns(3)
    uf = c1.selectbox("UF mencionada", ["(todas)"] + SIGLAS, key="uf_api")
    termo = c2.text_input("Termo", key="termo_api")
    parametros["limite"] = c3.number_input(
        "Limite", 1, 100, 10, key="limite_noticias_api"
    )
    if uf != "(todas)":
        parametros["uf"] = uf
    if termo:
        parametros["termo"] = termo

if st.button("Consultar", type="primary"):
    resposta = cliente_api.consultar(caminho, parametros)
    if not resposta.ok:
        st.error(f"{resposta.status or ''} {resposta.erro}")
    else:
        corpo = resposta.dados
        lista = (
            corpo
            if isinstance(corpo, list)
            else corpo.get("itens")
            if isinstance(corpo, dict)
            else None
        )
        if isinstance(lista, list) and lista:
            st.dataframe(pd.json_normalize(lista), hide_index=True, width="stretch")
        with st.expander("Resposta JSON", expanded=not isinstance(lista, list)):
            st.json(corpo)

# ═══════════════════ 3. Enviar notícia ═══════════════════

st.subheader("Enviar notícia (POST /noticias)")
st.markdown(
    "Adicione ao corpus uma notícia que os scrapers não cobrem. Com texto, ela entra como "
    "**integral**; sem texto, como **metadados**. No TP4, o modelo de linguagem vai resumir e "
    "classificar também essas notícias."
)
with st.form("form_noticia", clear_on_submit=False):
    c1, c2 = st.columns([2, 1])
    titulo = c1.text_input("Título *")
    fonte = c2.text_input("Fonte *", placeholder="ex.: Prefeitura de Caxias do Sul")
    c1, c2 = st.columns([2, 1])
    url = c1.text_input("URL *", placeholder="https://...")
    data_publicacao = c2.date_input(
        "Data de publicação *", value=date.today(), format="DD/MM/YYYY"
    )
    linha_fina = st.text_input("Linha fina (opcional)")
    texto = st.text_area(
        "Texto (opcional)",
        help="Só cole o texto integral se a licença da fonte permitir reprodução.",
    )
    enviar = st.form_submit_button("Enviar", type="primary")

if enviar:
    payload = {
        "fonte": fonte,
        "url": url,
        "titulo": titulo,
        "data_publicacao": data_publicacao.isoformat(),
        "linha_fina": linha_fina or None,
        "texto": texto or None,
    }
    resposta = cliente_api.enviar_noticia(payload)
    if resposta.ok:
        dados.carregar_corpus.clear()  # a notícia aparece na página Notícias
        registro = resposta.dados
        st.success(
            f"Notícia registrada (id {registro['id']}, nível {registro['nivel_texto']}). "
            f"UFs detectadas: {', '.join(registro['ufs_mencionadas']) or 'nenhuma'}."
        )
    elif resposta.status == 409:
        st.warning(resposta.erro)
    elif resposta.status == 422:
        st.error(f"Dados inválidos — {resposta.erro}")
    else:
        st.error(resposta.erro)

rodape()
