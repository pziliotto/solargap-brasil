"""
PROJETO: SolarGap Brasil
ARQUIVO: rotas/sistema.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026

DESCRIÇÃO:
    GET /       apresentação e lista de rotas
    GET /saude  verificação de funcionamento (usada pela página API do painel)
"""

from fastapi import APIRouter

from src.api.dependencias import RepositorioDep
from src.api.modelos import Erro, ResumoDados, Saude
from src.servicos import indicadores

VERSAO_API = "1.0.0"
roteador = APIRouter(tags=["Sistema"])


@roteador.get("/", summary="Apresentação da API")
def raiz() -> dict:
    return {
        "projeto": "SolarGap Brasil — Onde está o próximo mercado solar?",
        "versao": VERSAO_API,
        "documentacao": "/docs",
        "rotas": [
            "GET /saude",
            "GET /ufs",
            "GET /ufs/{sigla}",
            "GET /ranking",
            "GET /series/{sigla}",
            "GET /oportunidades",
            "GET /noticias",
            "GET /noticias/fontes",
            "GET /noticias/{id}",
            "POST /noticias",
            "GET /politicas/icms",
            "GET /politicas/icms/{sigla}",
            "POST /comparacoes",
        ],
    }


@roteador.get(
    "/saude",
    response_model=Saude,
    summary="Verifica se a API está no ar e com dados carregados",
    responses={
        503: {"model": Erro, "description": "Arquivos da camada Gold ausentes."}
    },
)
def saude(repositorio: RepositorioDep) -> Saude:
    ano_min, ano_max = indicadores.anos_disponiveis(repositorio.agregado)
    return Saude(
        status="ok",
        versao=VERSAO_API,
        carregado_em=repositorio.carregado_em,
        dados=ResumoDados(
            ufs=len(repositorio.dim_uf),
            linhas_agregado=len(repositorio.agregado),
            noticias=len(repositorio.corpus),
            icms=repositorio.icms is not None,
            periodo=f"{ano_min}-{ano_max}",
        ),
    )
