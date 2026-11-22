"""Dashboard multipáginas: todas as páginas executam e os filtros persistem entre páginas."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.servicos import potencial

# AppTest resolve caminhos relativos ao arquivo de teste: usa o caminho absoluto.
ARQUIVO_APP = str(Path(__file__).resolve().parents[1] / "src" / "app" / "app.py")

PAGINAS = [
    "inicio",
    "panorama",
    "evolucao",
    "oportunidades",
    "potencial",
    "noticias",
    "dados",
    "api",
    "laboratorio_ia",
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


def test_laboratorio_sem_servidor_mostra_instrucao(app, monkeypatch):
    monkeypatch.setenv("SOLARGAP_API_URL", "http://127.0.0.1:1")
    app.switch_page("paginas/laboratorio_ia.py").run()
    assert any("fora do ar" in e.value for e in app.error)
    assert any("uvicorn" in c.value for c in app.code)


def test_noticias_mostra_resumo_e_filtro_de_relevancia(app):
    app.switch_page("paginas/noticias.py").run()
    filtro = app.toggle(key="so_relevantes")
    if filtro.disabled:  # corpus_ia.csv ainda não gerado
        pytest.skip("corpus sem processamento por IA")
    total = int(app.metric[0].value)
    filtro.set_value(True).run()
    assert not app.exception
    assert int(app.metric[0].value) <= total


# ── Seletor de visão (três visões, todas as páginas) e página Potencial Solar ──


@pytest.mark.parametrize("pagina", PAGINAS)
def test_seletor_de_visao_em_todas_as_paginas(app, pagina):
    app.switch_page(f"paginas/{pagina}.py").run()
    seletor = app.sidebar.radio(key="visao")
    assert seletor.options == ["Visão corrigida (padrão)", "Critério ANEEL", "Limite conservador"]
    assert "COPEL-DIS" in seletor.help and "156" in seletor.help
    assert "atualizacao_base_10_2026.md" in seletor.help


def test_visao_persiste_e_muda_os_numeros(app):
    app.switch_page("paginas/panorama.py").run()
    app.sidebar.radio(key="visao").set_value("corrigida").run()
    corrigida = app.metric[0].value
    app.sidebar.radio(key="visao").set_value("conservadora").run()
    assert app.metric[0].value != corrigida  # potência instalada muda
    app.switch_page("paginas/noticias.py").run()
    app.switch_page("paginas/potencial.py").run()
    assert app.sidebar.radio(key="visao").value == "conservadora"
    assert "Limite conservador" in app.caption[0].value
    app.sidebar.radio(key="visao").set_value("corrigida").run()


def test_potencial_cards_iguais_ao_servico(app):
    app.switch_page("paginas/potencial.py").run()
    app.selectbox(key="pot_uf").set_value("Brasil").run()
    rotulos = [m.label for m in app.metric[:4]]
    assert rotulos == ["Potencial (x)", "Produção estimada (y)", "Gap (x − y)", "% realizado"]
    resumo = potencial.resumo_recorte(potencial.carregar_base(), "corrigida")
    esperado = f"{resumo['taxa_realizacao'] * 100:.1f}%".replace(".", ",")
    assert app.metric[3].value == esperado
    assert len(app.tabs) == 3


def test_potencial_filtro_de_municipio_depende_da_uf(app):
    app.switch_page("paginas/potencial.py").run()
    app.selectbox(key="pot_uf").set_value("Brasil").run()
    assert app.selectbox(key="pot_municipio").disabled
    app.selectbox(key="pot_uf").set_value("RS").run()
    app.selectbox(key="pot_municipio").set_value("4305108").run()
    assert not app.exception
    assert any(s.value == "Caxias do Sul (RS)" for s in app.subheader)
    # Trocar de UF devolve o município para "todos" (Caxias não existe no PR)
    app.selectbox(key="pot_uf").set_value("PR").run()
    assert not app.exception
    assert app.selectbox(key="pot_municipio").value == "todos"


def test_potencial_cenarios_trocam_de_ssp(app):
    app.switch_page("paginas/potencial.py").run()
    app.selectbox(key="pot_uf").set_value("BA").run()
    for cenario in ("ssp585", "ssp245"):
        app.radio(key="pot_cenario").set_value(cenario).run()
        assert not app.exception
    assert any("não previsão" in i.value for i in app.info)


def test_potencial_explicacao_separa_sinais_e_compara_com_o_esperado(app):
    app.switch_page("paginas/potencial.py").run()
    app.selectbox(key="pot_uf").set_value("RS").run()
    app.selectbox(key="pot_municipio").set_value("4305108").run()
    assert not app.exception
    rotulos = [m.label for m in app.metric]
    assert "Realiza" in rotulos and "Esperado pelo perfil" in rotulos
    textos = " ".join(m.value for m in app.markdown)
    assert "Abaixo do esperado" in textos
    assert "Puxam a taxa para baixo" in textos and "Puxam a taxa para cima" in textos
    assert "Renda: **+11,0 p.p.**" in textos
    assert any(e.label == "Detalhe por variável" for e in app.expander)
