"""
PROJETO: SolarGap Brasil
ARQUIVO: rotas/agente.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026 (TP5)

DESCRIÇÃO:
    Agente inteligente de apoio à decisão (src/agente):
        GET  /agente/status      provedor, modelo e se o LLM está no ar
        POST /agente/perguntar   pergunta -> diagnóstico, fatores, recomendações,
                                 ferramentas usadas e verificação dos números

MEMÓRIA:
    A rota não guarda sessão: o cliente envia o histórico e o campo contexto
    da resposta anterior (ver PedidoAgente).

ERROS:
    422  pergunta vazia, longa demais ou visão inválida
    503  Gold ausente (DadosIndisponiveis, tratado em main.py)
    Sem LLM no ar, a rota NÃO falha: responde no modo por regras e informa
    em "avisos" e "modo".
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from src.agente.agente import Agente
from src.agente.ferramentas import CATALOGO
from src.api.modelos import Erro, PedidoAgente, RespostaAgenteAPI, StatusAgente

roteador = APIRouter(prefix="/agente", tags=["Agente"])


def obter_agente(request: Request) -> Agente:
    """Cria o agente na primeira chamada e o reaproveita (lê a Gold uma vez)."""
    agente = getattr(request.app.state, "agente", None)
    if agente is None:
        agente = Agente.carregar()
        request.app.state.agente = agente
    return agente


AgenteDep = Annotated[Agente, Depends(obter_agente)]


@roteador.get(
    "/status", response_model=StatusAgente, summary="Estado do agente e do LLM"
)
def status(agente: AgenteDep) -> StatusAgente:
    config = agente.cliente.config
    return StatusAgente(
        provedor=config.provedor,
        modelo=config.modelo,
        url=config.url,
        llm_disponivel=agente.cliente.disponivel(),
        ferramentas=list(CATALOGO),
    )


@roteador.post(
    "/perguntar",
    response_model=RespostaAgenteAPI,
    summary="Pergunta ao agente de apoio à decisão",
    description=(
        "O agente localiza o recorte (UF ou município), escolhe as ferramentas (LLM ou "
        "regras), consulta a Gold (potencial, SHAP, oportunidades, cenários 2030–2050, "
        "ICMS e notícias), redige diagnóstico e recomendações e confere se cada número "
        "da resposta veio dos dados. Envie `historico` e `contexto` para perguntas de "
        'seguimento ("e Bento Gonçalves?").'
    ),
    responses={503: {"model": Erro, "description": "Gold ausente."}},
)
def perguntar(pedido: PedidoAgente, agente: AgenteDep) -> RespostaAgenteAPI:
    # def síncrono: a FastAPI executa numa thread, sem travar o servidor
    # enquanto o LLM responde.
    resposta = agente.perguntar(
        pedido.pergunta,
        historico=[t.model_dump() for t in pedido.historico],
        contexto=pedido.contexto,
        visao=pedido.visao.value,
        usar_llm=pedido.usar_llm,
    )
    return RespostaAgenteAPI(**resposta.como_dict())
