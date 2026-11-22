"""Rotas /potencial da API (Tarefa 7): modelos de resposta, parâmetro visao e erros."""

import pytest
from fastapi.testclient import TestClient

from src.api.dependencias import Repositorio, obter_repositorio
from src.api.main import app
from src.servicos import potencial

CAXIAS = "4305108"
VISOES = ["corrigida", "aneel", "conservadora"]


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    repositorio = Repositorio.carregar(pasta_external=tmp_path_factory.mktemp("ext"))
    app.dependency_overrides[obter_repositorio] = lambda: repositorio
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


@pytest.mark.parametrize("visao", VISOES)
def test_potencial_uf_nas_tres_visoes(cliente, visao):
    corpo = cliente.get(f"/potencial/uf?visao={visao}").json()
    assert corpo["visao"] == visao and len(corpo["itens"]) == 27
    assert corpo["premissas"]["performance_ratio"] == 0.75
    brasil = corpo["brasil"]
    assert brasil["nivel"] == "brasil" and brasil["n_municipios"] == 5570
    soma_y = sum(item["y_mwh_ano"] for item in corpo["itens"])
    assert soma_y == pytest.approx(brasil["y_mwh_ano"])
    assert all(len(item["principais_fatores"]) == 3 for item in corpo["itens"])


def test_visao_padrao_e_corrigida(cliente):
    padrao = cliente.get("/potencial/uf").json()
    corrigida = cliente.get("/potencial/uf?visao=corrigida").json()
    assert padrao["visao"] == "corrigida"
    assert padrao["brasil"] == corrigida["brasil"]


def test_municipio(cliente):
    corpo = cliente.get(f"/potencial/municipio/{CAXIAS}?visao=aneel").json()
    assert corpo["cod_ibge"] == CAXIAS and corpo["uf"] == "RS"
    assert corpo["nome"] == "Caxias do Sul (RS)" and corpo["nivel"] == "municipio"
    assert set(corpo["taxas_por_visao"]) == set(VISOES)
    assert corpo["taxa_realizacao"] == pytest.approx(corpo["taxas_por_visao"]["aneel"])


def test_explicacao_igual_ao_servico(cliente):
    base = potencial.carregar_base()
    corpo = cliente.get(f"/potencial/explicacao/{CAXIAS}").json()
    servico = potencial.explicar(base, cod_ibge=CAXIAS)
    assert [f["fator"] for f in corpo["fatores"]] == [
        f["fator"] for f in servico["fatores"]
    ]
    assert corpo["fatores"][0]["contribuicao_pp"] == pytest.approx(
        servico["fatores"][0]["contribuicao_pp"]
    )
    assert corpo["aviso_visao"] is None
    outra = cliente.get(f"/potencial/explicacao/{CAXIAS}?visao=conservadora").json()
    assert outra["aviso_visao"] and outra["visao_modelo"] == "corrigida"


def test_cenarios(cliente):
    corpo = cliente.get(f"/potencial/cenarios/{CAXIAS}?visao=aneel").json()
    assert corpo["visao"] == "aneel" and "não previsão" in corpo["aviso"]
    assert {(i["cenario"], i["janela"]) for i in corpo["itens"]} == {
        ("ssp245", "2030-2039"),
        ("ssp245", "2040-2050"),
        ("ssp585", "2030-2039"),
        ("ssp585", "2040-2050"),
    }
    for item in corpo["itens"]:
        assert item["delta_min"] <= item["delta_mediano"] <= item["delta_max"]
        assert item["taxa_projetada"] == pytest.approx(item["taxa_realizacao"])
        assert item["n_modelos"] == 5


@pytest.mark.parametrize(
    ("rota", "codigo"),
    [
        ("/potencial/municipio/9999999", 404),
        ("/potencial/explicacao/0000000", 404),
        ("/potencial/cenarios/abc", 404),
        ("/potencial/uf?visao=otimista", 422),
        (f"/potencial/municipio/{CAXIAS}?visao=ANEEL", 422),
        (f"/potencial/explicacao/{CAXIAS}?visao=", 422),
        (f"/potencial/cenarios/{CAXIAS}?visao=xyz", 422),
    ],
)
def test_codigos_de_erro(cliente, rota, codigo):
    resposta = cliente.get(rota)
    assert resposta.status_code == codigo
    assert "detail" in resposta.json()


def test_gold_de_potencial_ausente_responde_503(tmp_path):
    """Sem a Gold de potencial, só /potencial cai: o resto da API segue no ar."""
    repositorio = Repositorio.carregar(pasta_external=tmp_path)
    repositorio.pasta_processed = tmp_path  # pasta sem os parquets de potencial
    app.dependency_overrides[obter_repositorio] = lambda: repositorio
    with TestClient(app) as cliente:
        rotas = [
            "/potencial/uf",
            f"/potencial/municipio/{CAXIAS}",
            f"/potencial/explicacao/{CAXIAS}",
            f"/potencial/cenarios/{CAXIAS}",
        ]
        respostas = [cliente.get(rota) for rota in rotas]
        saude = cliente.get("/saude")
    app.dependency_overrides.clear()
    assert [r.status_code for r in respostas] == [503] * 4
    assert "potencial_municipal.parquet" in respostas[0].json()["detail"]
    assert saude.status_code == 200


def test_rotas_na_documentacao(cliente):
    caminhos = cliente.get("/openapi.json").json()["paths"]
    for rota in (
        "/potencial/uf",
        "/potencial/municipio/{cod_ibge}",
        "/potencial/explicacao/{cod_ibge}",
        "/potencial/cenarios/{cod_ibge}",
    ):
        parametros = {p["name"] for p in caminhos[rota]["get"]["parameters"]}
        assert "visao" in parametros
    assert "GET /potencial/uf" in cliente.get("/").json()["rotas"]
