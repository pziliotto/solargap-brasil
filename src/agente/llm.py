"""
PROJETO: SolarGap Brasil
ARQUIVO: agente/llm.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026 (TP5)

DESCRIÇÃO:
    Cliente mínimo do modelo de linguagem do agente, com dois provedores:

    ollama  (padrão) modelo local servido pelo Ollama, API nativa /api/chat.
            Coerente com o TP4 (tudo roda na máquina, sem custo por chamada).
            A API nativa permite fixar a janela de contexto (num_ctx), que a
            rota compatível com OpenAI do Ollama ignora.
    openai  qualquer serviço compatível com /v1/chat/completions (OpenAI,
            Groq, LM Studio, o próprio Ollama em /v1). Para quem preferir um
            modelo online, como o enunciado do TP5 permite.

CONFIGURAÇÃO (variáveis de ambiente):
    SOLARGAP_LLM_PROVEDOR   ollama | openai | nenhum   (padrão: ollama)
    SOLARGAP_LLM_MODELO     padrão: qwen2.5:7b
    SOLARGAP_LLM_URL        padrão: http://localhost:11434 (ollama) ou
                            https://api.openai.com/v1 (openai)
    SOLARGAP_LLM_API_KEY    só para o provedor openai
    SOLARGAP_LLM_TIMEOUT    segundos por chamada (padrão: 120)

POR QUE QWEN2.5-7B:
    No benchmark do TP4, o Qwen2.5-1.5B perdeu para modelos de tarefa em
    resumo. Aqui a tarefa é outra: escolher ferramentas (JSON) e redigir uma
    recomendação a partir de fatos prontos, sem precisar "saber" nada. O 7B
    quantizado (Q4, ~4,7 GB) cabe na GTX 1660 Ti de 6 GB e segue instruções em
    português bem melhor que o 1.5B. Alternativa leve: qwen2.5:3b (~2 GB).

FALHA:
    Qualquer erro de rede, tempo ou formato vira LLMIndisponivel. O agente
    trata isso caindo no modo por regras (agente.py), então o painel nunca
    quebra por falta do modelo.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

import httpx

PROVEDOR_PADRAO = "ollama"
MODELO_PADRAO = "qwen2.5:7b"
URL_PADRAO = {"ollama": "http://localhost:11434", "openai": "https://api.openai.com/v1"}
NUM_CTX = 8192


class LLMIndisponivel(RuntimeError):
    """Modelo fora do ar, lento demais ou com resposta inválida."""


@dataclass
class ConfigLLM:
    provedor: str = PROVEDOR_PADRAO
    modelo: str = MODELO_PADRAO
    url: str = URL_PADRAO[PROVEDOR_PADRAO]
    api_key: str | None = None
    timeout: float = 120.0

    @classmethod
    def do_ambiente(cls) -> ConfigLLM:
        provedor = os.getenv("SOLARGAP_LLM_PROVEDOR", PROVEDOR_PADRAO).strip().lower()
        return cls(
            provedor=provedor,
            modelo=os.getenv("SOLARGAP_LLM_MODELO", MODELO_PADRAO),
            url=os.getenv("SOLARGAP_LLM_URL", URL_PADRAO.get(provedor, "")).rstrip("/"),
            api_key=os.getenv("SOLARGAP_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
            timeout=float(os.getenv("SOLARGAP_LLM_TIMEOUT", "120")),
        )

    @property
    def descricao(self) -> str:
        return f"{self.modelo} via {self.provedor}"


class ClienteLLM:
    def __init__(self, config: ConfigLLM | None = None, transporte=None):
        self.config = config or ConfigLLM.do_ambiente()
        # transporte: httpx.MockTransport nos testes
        self._http = httpx.Client(timeout=self.config.timeout, transport=transporte)

    @property
    def ativo(self) -> bool:
        return self.config.provedor in ("ollama", "openai")

    def disponivel(self) -> bool:
        """Checagem rápida (2 s) de que o serviço responde e tem o modelo."""
        if not self.ativo:
            return False
        try:
            if self.config.provedor == "ollama":
                r = self._http.get(f"{self.config.url}/api/tags", timeout=2)
                r.raise_for_status()
                nomes = {m.get("name", "") for m in r.json().get("models", [])}
                alvo = self.config.modelo
                return any(n == alvo or n.split(":")[0] == alvo or n == f"{alvo}:latest"
                           for n in nomes)  # fmt: skip
            r = self._http.get(
                f"{self.config.url}/models", timeout=2, headers=self._cabecalhos()
            )
            return r.status_code == 200
        except (httpx.HTTPError, ValueError):
            return False

    def _cabecalhos(self) -> dict:
        if self.config.api_key:
            return {"Authorization": f"Bearer {self.config.api_key}"}
        return {}

    def conversar(
        self, mensagens: list[dict], json_mode: bool = False, temperatura: float = 0.2,
        max_tokens: int = 900,
    ) -> str:  # fmt: skip
        if not self.ativo:
            raise LLMIndisponivel("Nenhum provedor de LLM configurado.")
        try:
            if self.config.provedor == "ollama":
                corpo = {
                    "model": self.config.modelo,
                    "messages": mensagens,
                    "stream": False,
                    "options": {"temperature": temperatura, "num_ctx": NUM_CTX,
                                "num_predict": max_tokens},
                }  # fmt: skip
                if json_mode:
                    corpo["format"] = "json"
                r = self._http.post(f"{self.config.url}/api/chat", json=corpo)
                r.raise_for_status()
                texto = r.json()["message"]["content"]
            else:
                corpo = {
                    "model": self.config.modelo,
                    "messages": mensagens,
                    "temperature": temperatura,
                    "max_tokens": max_tokens,
                }
                if json_mode:
                    corpo["response_format"] = {"type": "json_object"}
                r = self._http.post(
                    f"{self.config.url}/chat/completions", json=corpo,
                    headers=self._cabecalhos(),
                )  # fmt: skip
                r.raise_for_status()
                texto = r.json()["choices"][0]["message"]["content"]
        except httpx.TimeoutException as erro:
            raise LLMIndisponivel(
                f"O modelo não respondeu em {self.config.timeout:.0f} s."
            ) from erro
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as erro:
            raise LLMIndisponivel(f"Falha ao chamar o modelo: {erro}") from erro
        if not texto or not texto.strip():
            raise LLMIndisponivel("O modelo devolveu resposta vazia.")
        return texto.strip()

    def conversar_json(self, mensagens: list[dict], **kwargs) -> dict:
        texto = self.conversar(mensagens, json_mode=True, temperatura=0.0, **kwargs)
        return extrair_json(texto)


def extrair_json(texto: str) -> dict:
    """Primeiro objeto JSON do texto (modelos pequenos às vezes o cercam de prosa)."""
    try:
        valor = json.loads(texto)
    except json.JSONDecodeError:
        achado = re.search(r"\{.*\}", texto, flags=re.DOTALL)
        if not achado:
            raise LLMIndisponivel("Resposta sem JSON.") from None
        try:
            valor = json.loads(achado.group(0))
        except json.JSONDecodeError as erro:
            raise LLMIndisponivel(f"JSON inválido: {erro}") from erro
    if not isinstance(valor, dict):
        raise LLMIndisponivel("O JSON devolvido não é um objeto.")
    return valor
