"""Dashboard multipáginas: todas as páginas executam e os filtros persistem entre páginas."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

# AppTest resolve caminhos relativos ao arquivo de teste: usa o caminho absoluto.
ARQUIVO_APP = str(Path(__file__).resolve().parents[1] / "src" / "app" / "app.py")

PAGINAS = [
    "inicio",
    "panorama",
    "evolucao",
    "oportunidades",
    "noticias",
    "dados",
    "api",
]


@pytest.fixture(scope="module")
def app():
    return AppTest.from_file(ARQUIVO_APP, default_timeout=120).run()


@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_executa_sem_erro(app, pagina):
    app.switch_page(f"paginas/{pagina}.py").run()
    assert not app.exception, [e.message for e in app.exception]
    assert app.title, "a página deve ter título"


def test_filtros_so_nas_paginas_de_analise(app):
    app.switch_page("paginas/panorama.py").run()
    assert app.sidebar.selectbox(key="metrica")
    app.switch_page("paginas/noticias.py").run()
    assert not any(w.key == "metrica" for w in app.sidebar.selectbox)


def test_filtro_persiste_ao_trocar_de_pagina(app):
    app.switch_page("paginas/panorama.py").run()
    app.sidebar.selectbox(key="metrica").set_value("potencia_mw").run()
    app.switch_page("paginas/noticias.py").run()  # página sem filtros
    app.switch_page("paginas/panorama.py").run()
    assert app.sidebar.selectbox(key="metrica").value == "potencia_mw"


def test_pagina_api_sem_servidor_mostra_instrucao(app, monkeypatch):
    monkeypatch.setenv("SOLARGAP_API_URL", "http://127.0.0.1:1")
    app.switch_page("paginas/api.py").run()
    assert any("uvicorn" in e.value for e in app.error) or app.code
