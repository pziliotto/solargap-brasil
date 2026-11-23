"""Teste de fumaça do painel: cada página do menu executa sem levantar exceção.

Usa streamlit.testing.v1.AppTest, que roda o script de verdade (com os dados
versionados do projeto), sem navegador. A lista de páginas é lida do próprio
menu (src/app/app.py), então uma página nova entra no teste automaticamente.

As páginas API e Laboratório de IA dependem da API em outro processo. Aqui o
endereço aponta para uma porta fechada: o teste confirma que, sem a API, a
página mostra o aviso em vez de quebrar.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "src" / "app" / "app.py"
PAGINAS = re.findall(r'st\.Page\("([^"]+)"', APP.read_text(encoding="utf-8"))
TEMPO_LIMITE_S = 120


def test_menu_lista_as_paginas():
    assert len(PAGINAS) == 10 and "paginas/agente.py" in PAGINAS
    for pagina in PAGINAS:
        assert (APP.parent / pagina).exists(), pagina


@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_executa_sem_excecao(pagina, monkeypatch):
    monkeypatch.setenv("SOLARGAP_API_URL", "http://127.0.0.1:9")  # porta fechada
    app = AppTest.from_file(str(APP), default_timeout=TEMPO_LIMITE_S)
    app.run()
    app.switch_page(pagina).run()
    assert not app.exception, f"{pagina}: {[e.message for e in app.exception]}"
    assert app.title, f"{pagina}: nada foi desenhado (a troca de página falhou?)"
    assert not app.error or pagina in {"paginas/api.py", "paginas/laboratorio_ia.py"}, (
        f"{pagina}: {[e.value for e in app.error]}"
    )
