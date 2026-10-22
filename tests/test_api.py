"""API FastAPI: rotas, modelos de resposta e códigos de erro."""

import pytest
from fastapi.testclient import TestClient

from src.api.dependencias import Repositorio, obter_repositorio
from src.api.main import app
from src.servicos import dados


@pytest.fixture
def cliente(tmp_path):
    """Cliente com repositório real de leitura e pasta de envios temporária."""
    repositorio = Repositorio.carregar(pasta_external=tmp_path)
    app.dependency_overrides[obter_repositorio] = lambda: repositorio
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


def test_saude(cliente):
    resposta = cliente.get("/saude")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ok" and corpo["dados"]["ufs"] == 27


def test_ufs_e_detalhe(cliente):
    assert len(cliente.get("/ufs").json()["itens"]) == 27
    detalhe = cliente.get("/ufs/rs").json()
    assert detalhe["indicadores"]["sigla_uf"] == "RS"
    assert set(detalhe["posicoes"]) == {
        "watts_por_habitante",
        "empreendimentos_por_100k_hab",
        "potencia_mw",
        "qtd_empreendimentos",
    }
    assert detalhe["quadrante"] in {
        "Líder em expansão",
        "Mercado maduro",
        "Mercado emergente",
        "Lacuna persistente",
    }


@pytest.mark.parametrize(
    ("rota", "codigo"),
    [
        ("/ufs/XX", 404),
        ("/noticias/inexistente", 404),
        ("/ranking?ano_inicio=2025&ano_fim=2020", 400),
        ("/ufs?classes=Inexistente", 400),
        ("/ranking?metrica=invalida", 422),
        ("/ranking?limite=99", 422),
        ("/noticias?desde=2026-01-01&ate=2025-01-01", 400),
        ("/oportunidades?ano_base=2026&ano_final=2026", 400),
    ],
)
def test_codigos_de_erro(cliente, rota, codigo):
    resposta = cliente.get(rota)
    assert resposta.status_code == codigo
    assert "detail" in resposta.json()


def test_ranking_ordenado(cliente):
    itens = cliente.get("/ranking?metrica=potencia_mw&limite=5").json()["itens"]
    assert [i["posicao"] for i in itens] == [1, 2, 3, 4, 5]
    assert itens[0]["valor"] >= itens[-1]["valor"]
    ascendente = cliente.get("/ranking?metrica=potencia_mw&ordem=asc&limite=1").json()[
        "itens"
    ]
    assert ascendente[0]["posicao"] == 27


def test_series_e_oportunidades(cliente):
    serie = cliente.get("/series/MA?ano_inicio=2020&ano_fim=2025").json()
    assert [p["ano"] for p in serie["pontos"]] == list(range(2020, 2026))
    oportunidades = cliente.get("/oportunidades").json()
    assert len(oportunidades["itens"]) == 27 and oportunidades["ano_final"] == 2025


def test_noticias_paginacao(cliente):
    pagina = cliente.get("/noticias?limite=5&deslocamento=5").json()
    assert pagina["limite"] == 5 and len(pagina["itens"]) == 5 and pagina["total"] >= 10
    detalhe = cliente.get(f"/noticias/{pagina['itens'][0]['id']}").json()
    assert detalhe["texto_para_modelo"].startswith(detalhe["titulo"])


def test_post_noticia_criacao_duplicidade_validacao(cliente, tmp_path):
    nova = {
        "fonte": "Teste",
        "url": "https://exemplo.org/solar-no-amapa",
        "titulo": "Energia solar avança no Amapá",
        "data_publicacao": "2026-03-01",
        "texto": "O Amapá registrou crescimento da geração distribuída no último ano.",
    }
    criada = cliente.post("/noticias", json=nova)
    assert criada.status_code == 201
    assert criada.json()["nivel_texto"] == "integral" and criada.json()[
        "ufs_mencionadas"
    ] == ["AP"]
    assert dados.carregar_noticias_enviadas(tmp_path).shape[0] == 1
    assert (
        cliente.get(f"/noticias/{criada.json()['id']}").status_code == 200
    )  # corpus recarregado

    assert cliente.post("/noticias", json=nova).status_code == 409

    invalida = {
        **nova,
        "url": "nao-e-url",
        "data_publicacao": "2099-01-01",
        "titulo": "curto",
    }
    resposta = cliente.post("/noticias", json=invalida)
    assert resposta.status_code == 422
    campos = {erro["loc"][-1] for erro in resposta.json()["detail"]}
    assert {"url", "data_publicacao", "titulo"} <= campos


def test_comparacoes(cliente):
    pedido = {
        "nome_indicador": "clientes",
        "valores": {"rs": 120, "SC": 85, "PR": 60, "SP": 40},
    }
    resposta = cliente.post("/comparacoes", json=pedido)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["n_ufs"] == 4 and -1 <= corpo["correlacao_spearman"] <= 1
    assert (
        cliente.post(
            "/comparacoes", json={**pedido, "valores": {"ZZ": 1, "RS": 2, "SC": 3}}
        ).status_code
        == 422
    )
    assert (
        cliente.post("/comparacoes", json={**pedido, "valores": {"RS": 1}}).status_code
        == 422
    )


def test_politicas_icms(cliente):
    resposta = cliente.get("/politicas/icms")
    if dados.carregar_icms() is None:
        assert resposta.status_code == 503
        return
    assert resposta.status_code == 200 and len(resposta.json()) == 27
    assert cliente.get("/politicas/icms/pa").json()["convenio_adesao"] == "81/16"


def test_api_sem_dados_responde_503(tmp_path):
    app.dependency_overrides[obter_repositorio] = lambda: Repositorio.carregar(
        pasta_processed=tmp_path
    )
    with TestClient(app) as cliente:
        resposta = cliente.get("/saude")
    app.dependency_overrides.clear()
    assert resposta.status_code == 503
