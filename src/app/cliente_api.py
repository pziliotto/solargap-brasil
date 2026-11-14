"""
PROJETO: SolarGap Brasil
ARQUIVO: cliente_api.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Cliente HTTP do dashboard para a API do projeto (src/api). Usado pela página
    "API": verificação de status, consultas GET e envio de notícias (POST).

ENDEREÇO DA API:
    Variável de ambiente SOLARGAP_API_URL; padrão http://127.0.0.1:8000, o
    endereço do uvicorn rodando localmente:
        uvicorn src.api.main:app --reload

CONTRATO:
    Nenhuma função levanta exceção para quem chama. Toda chamada devolve um
    RespostaAPI com ok/status/dados/erro, e a página decide como exibir. API
    fora do ar é uma situação esperada (o painel funciona sem ela), não um erro
    de programação.

TIMEOUT CURTO:
    3 segundos para conectar e 10 para ler: se a API não responder, o usuário
    recebe a mensagem rapidamente, em vez de uma página travada.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

URL_PADRAO = "http://127.0.0.1:8000"
TIMEOUT = (3, 10)


def url_base() -> str:
    return os.environ.get("SOLARGAP_API_URL", URL_PADRAO).rstrip("/")


@dataclass
class RespostaAPI:
    ok: bool
    status: int | None = None
    dados: Any = None
    erro: str | None = None


def _detalhe_erro(resposta: requests.Response) -> str:
    """Extrai a mensagem do corpo de erro da API (campo detail)."""
    try:
        corpo = resposta.json()
    except ValueError:
        return resposta.text[:300] or f"HTTP {resposta.status_code}"

    detalhe = corpo.get("detail", corpo) if isinstance(corpo, dict) else corpo
    if isinstance(detalhe, list):  # erros de validação (422)
        return "; ".join(
            f"{'.'.join(str(p) for p in item.get('loc', [])[1:])}: {item.get('msg')}"
            for item in detalhe
        )
    return str(detalhe)


def _requisitar(metodo: str, caminho: str, **kwargs) -> RespostaAPI:
    url = f"{url_base()}{caminho}"
    try:
        resposta = requests.request(metodo, url, timeout=TIMEOUT, **kwargs)
    except requests.exceptions.ConnectionError:
        return RespostaAPI(
            ok=False,
            erro=f"API fora do ar em {url_base()}. Inicie com: uvicorn src.api.main:app --reload",
        )
    except requests.exceptions.Timeout:
        return RespostaAPI(ok=False, erro="A API não respondeu dentro do tempo limite.")
    except requests.exceptions.RequestException as erro:
        return RespostaAPI(ok=False, erro=f"Falha na requisição: {erro}")

    if resposta.ok:
        return RespostaAPI(ok=True, status=resposta.status_code, dados=resposta.json())
    return RespostaAPI(
        ok=False, status=resposta.status_code, erro=_detalhe_erro(resposta)
    )


def saude() -> RespostaAPI:
    return _requisitar("GET", "/saude")


def consultar(caminho: str, parametros: dict | None = None) -> RespostaAPI:
    """GET genérico, usado pelo explorador de rotas da página API."""
    return _requisitar("GET", caminho, params=parametros or {})


def enviar_noticia(payload: dict) -> RespostaAPI:
    return _requisitar("POST", "/noticias", json=payload)
