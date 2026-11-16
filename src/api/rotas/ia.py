"""
PROJETO: SolarGap Brasil
ARQUIVO: rotas/ia.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 16/11/2026

DESCRIÇÃO:
    Rotas dos modelos de linguagem locais (TP4):
        GET  /ia/status                 estado de carga de cada modelo
        POST /processar_texto           resumo, relevância e tom de um texto livre
        POST /noticias/{id}/processar   o mesmo, para uma notícia do corpus

ERROS (formato {"detail": ...}, como no resto da API):
    404  notícia inexistente
    422  entrada inválida (texto curto, tarefa desconhecida...) — Pydantic
    503  modelo não carregado, carregando (com cabeçalho Retry-After) ou com
         falha de carga — tratado em main.py a partir de ModeloIndisponivel
    504  inferência passou do tempo limite (SOLARGAP_TIMEOUT_INFERENCIA)
    500  erro inesperado durante a inferência — registrado no log

POR QUE ROTAS async COM A INFERÊNCIA EM THREAD:
    A inferência bloqueia por segundos. Rodando em uma thread, o servidor
    continua atendendo /saude e /ia/status enquanto isso, e asyncio.wait_for
    permite devolver 504 quando o tempo estoura. A thread em si não é
    interrompida (PyTorch não permite); a fila do gerenciador garante que a
    próxima inferência só começa quando ela termina.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.api.dependencias import RepositorioDep, registros
from src.api.modelos import (
    Erro,
    EstadoTarefaIA,
    ModeloUsado,
    PedidoProcessamento,
    RespostaProcessamento,
    ResultadoRelevanciaIA,
    ResultadoResumoIA,
    ResultadosIA,
    ResultadoTomIA,
    StatusIA,
    TarefaIA,
)
from src.ia import catalogo
from src.ia.catalogo import Tarefa
from src.ia.motor import GerenciadorModelos
from src.servicos.texto import texto_para_modelo

TIMEOUT_PADRAO_S = 60.0
roteador = APIRouter(tags=["IA"])

RESPOSTAS_ERRO = {
    503: {
        "model": Erro,
        "description": "Modelo não carregado, carregando ou com falha de carga.",
    },
    504: {"model": Erro, "description": "A inferência passou do tempo limite."},
}


def timeout_inferencia() -> float:
    return float(os.getenv("SOLARGAP_TIMEOUT_INFERENCIA", TIMEOUT_PADRAO_S))


def obter_gerenciador(request: Request) -> GerenciadorModelos:
    """Gerenciador criado no startup. Sem ele, as rotas respondem 503 (não carregado)."""
    gerenciador = getattr(request.app.state, "ia", None)
    if gerenciador is None:
        gerenciador = GerenciadorModelos()
        request.app.state.ia = gerenciador
    return gerenciador


GerenciadorDep = Annotated[GerenciadorModelos, Depends(obter_gerenciador)]


# ═══════════════════ Status ═══════════════════


@roteador.get(
    "/ia/status", response_model=StatusIA, summary="Estado dos modelos de linguagem"
)
def status_ia(gerenciador: GerenciadorDep) -> StatusIA:
    tarefas = []
    for tarefa in Tarefa:
        situacao = gerenciador.situacao(tarefa)
        tarefas.append(
            EstadoTarefaIA(
                tarefa=TarefaIA(tarefa.value),
                modelo=situacao.config.hf_id,
                estado=situacao.estado.value,
                experimental=tarefa in catalogo.TAREFAS_EXPERIMENTAIS,
                segundos_carga=situacao.segundos_carga,
                carregado_em=situacao.carregado_em,
                erro=situacao.erro,
            )
        )
    return StatusIA(
        pronto=gerenciador.todas_prontas(),
        dispositivo=gerenciador.dispositivo,
        timeout_inferencia_s=timeout_inferencia(),
        tarefas=tarefas,
    )


# ═══════════════════ Processamento ═══════════════════


def _executar(
    gerenciador: GerenciadorModelos, texto: str, tarefas: list[TarefaIA]
) -> ResultadosIA:
    """Roda as tarefas pedidas (em thread). ModeloIndisponivel sobe para o 503."""
    resultados = ResultadosIA()
    for tarefa in tarefas:
        if tarefa == TarefaIA.resumo:
            r = gerenciador.resumir(texto)
            resultados.resumo = ResultadoResumoIA(**r.como_dict())
        elif tarefa == TarefaIA.relevancia:
            r = gerenciador.avaliar_relevancia(texto)
            resultados.relevancia = ResultadoRelevanciaIA(
                **r.como_dict(), limiar=catalogo.LIMIAR_RELEVANCIA
            )
        elif tarefa == TarefaIA.tom:
            r = gerenciador.classificar_tom(texto)
            resultados.tom = ResultadoTomIA(**r.como_dict(), aviso=catalogo.AVISO_TOM)
    return resultados


async def _processar(
    gerenciador: GerenciadorModelos, texto: str, tarefas: list[TarefaIA], origem: str
) -> RespostaProcessamento:
    # Checagem antecipada: com o modelo indisponível, responde 503 na hora,
    # sem ocupar uma thread.
    for tarefa in tarefas:
        gerenciador.verificar(Tarefa(tarefa.value))

    inicio = time.perf_counter()
    limite = timeout_inferencia()
    try:
        resultados = await asyncio.wait_for(
            asyncio.to_thread(_executar, gerenciador, texto, tarefas), timeout=limite
        )
    except TimeoutError as erro:
        raise HTTPException(
            status_code=504,
            detail=(
                f"A inferência passou de {limite:.0f} s. Tente um texto menor, menos tarefas "
                "ou aumente SOLARGAP_TIMEOUT_INFERENCIA."
            ),
        ) from erro

    modelos = [
        ModeloUsado(
            tarefa=t,
            modelo=gerenciador.configs[Tarefa(t.value)].hf_id,
            licenca=gerenciador.configs[Tarefa(t.value)].licenca,
        )
        for t in tarefas
    ]
    return RespostaProcessamento(
        origem=origem,
        tarefas=tarefas,
        caracteres_entrada=len(texto),
        resultados=resultados,
        modelos=modelos,
        dispositivo=gerenciador.dispositivo or "desconhecido",
        duracao_ms=round(1000 * (time.perf_counter() - inicio)),
    )


@roteador.post(
    "/processar_texto",
    response_model=RespostaProcessamento,
    response_model_exclude_none=True,
    summary="Processa um texto com os modelos locais",
    description=(
        "Executa as tarefas pedidas sobre o texto enviado: **resumo** (PTT5), **relevancia** "
        "(trata de energia solar? — mDeBERTa zero-shot) e **tom** (experimental). Os modelos "
        "rodam na máquina da API, sem serviço externo. Textos longos são truncados no limite "
        "de 512 tokens, e a resposta informa quando isso acontece."
    ),
    responses={**RESPOSTAS_ERRO, 422: {"description": "Texto ou tarefas inválidos."}},
)
async def processar_texto(
    pedido: PedidoProcessamento, gerenciador: GerenciadorDep
) -> RespostaProcessamento:
    return await _processar(gerenciador, pedido.texto, pedido.tarefas, origem="texto")


@roteador.post(
    "/noticias/{id_noticia}/processar",
    response_model=RespostaProcessamento,
    response_model_exclude_none=True,
    summary="Processa uma notícia do corpus com os modelos locais",
    description=(
        "Mesma análise de POST /processar_texto, usando como entrada o texto_para_modelo da "
        "notícia (título, linha fina e texto, conforme o nível de texto da fonte) — a mesma "
        "entrada do processamento em lote."
    ),
    responses={
        **RESPOSTAS_ERRO,
        404: {"model": Erro, "description": "Id inexistente."},
    },
)
async def processar_noticia(
    id_noticia: str,
    repositorio: RepositorioDep,
    gerenciador: GerenciadorDep,
    tarefas: Annotated[
        list[TarefaIA] | None,
        Query(
            description="Repita o parâmetro para várias tarefas. Padrão: resumo e relevancia."
        ),
    ] = None,
) -> RespostaProcessamento:
    linha = repositorio.corpus[repositorio.corpus["id"] == id_noticia]
    if linha.empty:
        raise HTTPException(
            status_code=404, detail=f"Notícia '{id_noticia}' não encontrada."
        )
    noticia = registros(linha)[0]
    texto = texto_para_modelo(
        noticia["titulo"],
        noticia.get("linha_fina"),
        noticia.get("texto"),
        noticia["nivel_texto"],
    )
    escolhidas = list(dict.fromkeys(tarefas or [TarefaIA.resumo, TarefaIA.relevancia]))
    return await _processar(
        gerenciador, texto, escolhidas, origem=f"noticia:{id_noticia}"
    )
