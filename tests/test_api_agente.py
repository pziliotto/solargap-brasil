"""Rotas /agente (TP5): response model, memória entre chamadas e erros."""

import pytest
from fastapi.testclient import TestClient

from src.agente.agente import Agente
from src.agente.llm import ClienteLLM, ConfigLLM
from src.api.main import app
from src.api.rotas.agente import obter_agente


@pytest.fixture(scope="module")
def cliente():
    agente = Agente.carregar(cliente=ClienteLLM(ConfigLLM(provedor="nenhum")))
    app.dependency_overrides[obter_agente] = lambda: agente
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


def test_status(cliente):
    corpo = cliente.get("/agente/status").json()
    assert corpo["provedor"] == "nenhum" and corpo["llm_disponivel"] is False
    assert "oportunidades" in corpo["ferramentas"]


def test_perguntar_e_seguir_a_conversa(cliente):
    primeira = cliente.post(
        "/agente/perguntar", json={"pergunta": "Onde investir no Paraná?"}
    )
    assert primeira.status_code == 200
    corpo = primeira.json()
    assert corpo["modo"] == "regras" and corpo["recorte"]["uf"] == "PR"
    assert corpo["verificacao"]["taxa"] == 1.0 and corpo["ferramentas"]
    seguinte = cliente.post(
        "/agente/perguntar",
        json={
            "pergunta": "E os cenários climáticos?",
            "historico": [
                {"pergunta": corpo["pergunta"], "resposta": corpo["resposta"]}
            ],
            "contexto": corpo["contexto"],
        },
    ).json()
    assert seguinte["recorte_herdado"] and seguinte["recorte"]["uf"] == "PR"


@pytest.mark.parametrize(
    "corpo",
    [
        {"pergunta": "   "},
        {"pergunta": "ok"},
        {"pergunta": "Como está o RS?", "visao": "x"},
        {},
    ],
)
def test_entrada_invalida_422(cliente, corpo):
    assert cliente.post("/agente/perguntar", json=corpo).status_code == 422
