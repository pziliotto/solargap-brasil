"""
PROJETO: SolarGap Brasil
ARQUIVO: main.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO: 16/11/2026 — TP4: rotas de IA, carga dos modelos em segundo plano,
             503 com Retry-After para modelo indisponível
             22/11/2026 — TP4.5, Tarefa 7: rotas /potencial

DESCRIÇÃO:
    Aplicação FastAPI: metadados da documentação, registro das rotas, carga
    única dos dados no startup e tratamento centralizado de erros.

TRATAMENTO DE ERROS (todas as respostas de erro têm o formato {"detail": ...}):
    400  FiltroInvalido      — filtros incoerentes (ex.: ano_inicio > ano_fim)
    404  HTTPException       — UF, notícia ou município (código IBGE) inexistente
    409  HTTPException       — notícia com URL já existente
    422  validação Pydantic  — campos inválidos, com a lista campo a campo
    503  DadosIndisponiveis  — arquivo obrigatório da Gold ausente
    503  ModeloIndisponivel  — modelo de linguagem carregando (Retry-After) ou
                               com falha de carga (TP4)
    504  HTTPException       — inferência acima do tempo limite (TP4)
    500  qualquer outro erro — registrado no log; o cliente recebe mensagem
                               genérica, sem rastro de pilha (não expõe código)

MODELOS DE LINGUAGEM (TP4):
    No startup, os modelos começam a carregar em uma thread. A API sobe na
    hora: enquanto carregam, as rotas de IA respondem 503 com Retry-After, e o
    resto da API funciona normalmente. SOLARGAP_CARREGAR_MODELOS=0 desliga a
    carga (testes, máquinas sem PyTorch).

EXECUÇÃO (a partir da raiz):
    uvicorn src.api.main:app --reload
    Documentação: http://127.0.0.1:8000/docs  (Swagger)  ·  /redoc
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from src.api.dependencias import Repositorio  # noqa: E402
from src.api.rotas import (  # noqa: E402
    comparacoes,
    ia,
    indicadores,
    noticias,
    politicas,
    potencial,
    sistema,
)
from src.ia.motor import GerenciadorModelos, ModeloIndisponivel  # noqa: E402
from src.servicos.dados import DadosIndisponiveis  # noqa: E402
from src.servicos.indicadores import FiltroInvalido  # noqa: E402

logger = logging.getLogger("solargap.api")

DESCRICAO = """
API do **SolarGap Brasil — Onde está o próximo mercado solar?**

Expõe os dados tratados do projeto (camada Gold: ANEEL + IBGE), o corpus de notícias e a
adesão estadual ao Convênio ICMS 16/15. Os cálculos são os mesmos do dashboard Streamlit
(camada `src/servicos`).

* **Indicadores** — watts por habitante, empreendimentos por 100 mil habitantes, ranking,
  séries, crescimento do parque e matriz de oportunidade.
* **Notícias** — consulta paginada e envio de novas notícias (POST).
* **Políticas públicas** — adesão ao Convênio ICMS 16/15.
* **Comparações** — cruzamento de um indicador próprio com a adoção solar (POST).
* **Potencial solar** — potencial técnico residencial, produção estimada, gap e taxa de
  realização por UF e município; fatores associados (SHAP) e cenários de irradiação
  2030–2050. Parâmetro `visao`: corrigida (padrão), aneel ou conservadora.
* **IA** — resumo e relevância de textos com modelos de linguagem locais (HuggingFace),
  sem serviço externo. Tom em caráter experimental.

Fontes: ANEEL (ODbL), IBGE — Censo 2022, Agência Brasil e Agência Gov (EBC), CONFAZ.
"""

TAGS = [
    {"name": "Sistema", "description": "Apresentação e verificação de funcionamento."},
    {
        "name": "Indicadores",
        "description": "Adoção de energia solar distribuída por UF.",
    },
    {
        "name": "Notícias",
        "description": "Corpus de notícias — base do processamento por LLM no TP4.",
    },
    {"name": "Políticas públicas", "description": "Convênio ICMS 16/15 (CONFAZ)."},
    {
        "name": "Comparações",
        "description": "Cruzamento de indicadores do usuário com a adoção.",
    },
    {
        "name": "Potencial solar",
        "description": "Potencial x produção, fatores (SHAP) e cenários 2030–2050 (TP4.5).",
    },
    {
        "name": "IA",
        "description": "Modelos de linguagem locais (PTT5 e mDeBERTa) — TP4.",
    },
]


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    """Lê a Gold uma vez no startup. Se faltar arquivo, a API sobe e responde 503."""
    try:
        app.state.repositorio = Repositorio.carregar()
        logger.info("Dados carregados: %d notícias.", len(app.state.repositorio.corpus))
    except DadosIndisponiveis as erro:
        logger.error("API iniciada sem dados: %s", erro)
        app.state.repositorio = None

    try:
        app.state.ia = GerenciadorModelos()
    except ValueError as erro:  # modelo inválido na variável de ambiente
        logger.error("Configuração de modelos inválida: %s", erro)
        app.state.ia = None
    if app.state.ia and os.getenv("SOLARGAP_CARREGAR_MODELOS", "1") != "0":
        app.state.ia.carregar(em_segundo_plano=True)
        logger.info("Carga dos modelos de linguagem iniciada em segundo plano.")
    yield


app = FastAPI(
    title="SolarGap Brasil API",
    version=sistema.VERSAO_API,
    description=DESCRICAO,
    openapi_tags=TAGS,
    lifespan=ciclo_de_vida,
    contact={"name": "Pâmela Lima Ziliotto"},
    license_info={
        "name": "Dados ANEEL sob ODbL 1.0",
        "url": "http://opendatacommons.org/licenses/odbl/1.0/",
    },
)

for modulo in (sistema, indicadores, potencial, noticias, politicas, comparacoes, ia):
    app.include_router(modulo.roteador)


@app.exception_handler(FiltroInvalido)
async def tratar_filtro_invalido(_: Request, erro: FiltroInvalido) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(erro)})


@app.exception_handler(DadosIndisponiveis)
async def tratar_dados_indisponiveis(
    _: Request, erro: DadosIndisponiveis
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(erro)})


@app.exception_handler(ModeloIndisponivel)
async def tratar_modelo_indisponivel(
    _: Request, erro: ModeloIndisponivel
) -> JSONResponse:
    cabecalhos = {"Retry-After": str(erro.retry_after)} if erro.retry_after else None
    return JSONResponse(
        status_code=503, content={"detail": str(erro)}, headers=cabecalhos
    )


@app.exception_handler(Exception)
async def tratar_erro_inesperado(requisicao: Request, erro: Exception) -> JSONResponse:
    logger.exception("Erro inesperado em %s %s", requisicao.method, requisicao.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Erro interno inesperado. O ocorrido foi registrado no log da API."
        },
    )
