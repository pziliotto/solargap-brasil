"""
PROJETO: SolarGap Brasil
ARQUIVO: main.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Aplicação FastAPI: metadados da documentação, registro das rotas, carga
    única dos dados no startup e tratamento centralizado de erros.

TRATAMENTO DE ERROS (todas as respostas de erro têm o formato {"detail": ...}):
    400  FiltroInvalido      — filtros incoerentes (ex.: ano_inicio > ano_fim)
    404  HTTPException       — UF ou notícia inexistente
    409  HTTPException       — notícia com URL já existente
    422  validação Pydantic  — campos inválidos, com a lista campo a campo
    503  DadosIndisponiveis  — arquivo obrigatório da Gold ausente
    500  qualquer outro erro — registrado no log; o cliente recebe mensagem
                               genérica, sem rastro de pilha (não expõe código)

    O TP4 pede exatamente esse padrão para a rota do modelo de linguagem
    (ex.: 503 quando o modelo não carregar). A estrutura já está pronta.

EXECUÇÃO (a partir da raiz):
    uvicorn src.api.main:app --reload
    Documentação: http://127.0.0.1:8000/docs  (Swagger)  ·  /redoc
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from src.api.dependencias import Repositorio  # noqa: E402
from src.api.rotas import comparacoes, indicadores, noticias, politicas, sistema  # noqa: E402
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

for modulo in (sistema, indicadores, noticias, politicas, comparacoes):
    app.include_router(modulo.roteador)


@app.exception_handler(FiltroInvalido)
async def tratar_filtro_invalido(_: Request, erro: FiltroInvalido) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(erro)})


@app.exception_handler(DadosIndisponiveis)
async def tratar_dados_indisponiveis(
    _: Request, erro: DadosIndisponiveis
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(erro)})


@app.exception_handler(Exception)
async def tratar_erro_inesperado(requisicao: Request, erro: Exception) -> JSONResponse:
    logger.exception("Erro inesperado em %s %s", requisicao.method, requisicao.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Erro interno inesperado. O ocorrido foi registrado no log da API."
        },
    )
