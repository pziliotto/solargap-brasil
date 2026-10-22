"""
PROJETO: SolarGap Brasil
ARQUIVO: rotas/politicas.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026

DESCRIÇÃO:
    GET /politicas/icms          adesão das 27 UFs ao Convênio ICMS 16/15
    GET /politicas/icms/{sigla}  adesão de uma UF

    Dado gerado por src/data_acquisition/icms_confaz.py. Enquanto o arquivo não
    existir, as rotas respondem 503 com a instrução para gerá-lo.
"""

from fastapi import APIRouter, HTTPException

from src.api.dependencias import RepositorioDep, registros
from src.api.modelos import AdesaoICMS, Erro

roteador = APIRouter(prefix="/politicas", tags=["Políticas públicas"])
MENSAGEM_AUSENTE = (
    "Tabela de ICMS ainda não gerada. Rode: python -m src.data_acquisition.icms_confaz"
)


def _tabela(repositorio):
    if repositorio.icms is None:
        raise HTTPException(status_code=503, detail=MENSAGEM_AUSENTE)
    return repositorio.icms


@roteador.get(
    "/icms",
    response_model=list[AdesaoICMS],
    summary="Adesão das UFs ao Convênio ICMS 16/15",
    responses={503: {"model": Erro, "description": "Tabela ainda não gerada."}},
)
def listar_icms(repositorio: RepositorioDep) -> list[AdesaoICMS]:
    tabela = _tabela(repositorio).sort_values("inicio_efeitos")
    return [AdesaoICMS(**item) for item in registros(tabela)]


@roteador.get(
    "/icms/{sigla}",
    response_model=AdesaoICMS,
    summary="Adesão de uma UF ao Convênio ICMS 16/15",
    responses={
        404: {"model": Erro, "description": "Sigla inexistente."},
        503: {"model": Erro, "description": "Tabela ainda não gerada."},
    },
)
def detalhar_icms(sigla: str, repositorio: RepositorioDep) -> AdesaoICMS:
    tabela = _tabela(repositorio)
    linha = tabela[tabela["sigla_uf"] == sigla.upper()]
    if linha.empty:
        raise HTTPException(
            status_code=404, detail=f"UF '{sigla.upper()}' não encontrada."
        )
    return AdesaoICMS(**registros(linha)[0])
