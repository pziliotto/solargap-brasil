"""Scrapers de notícias: extração, robots.txt, RSS só com metadados e mescla do corpus."""

from collections import Counter
from datetime import datetime

import pandas as pd
import pytest

from src.data_acquisition.noticias import coletor
from src.data_acquisition.noticias.base import converter_data, normalizar_titulo
from src.data_acquisition.noticias.fontes import (
    AGENCIA_BRASIL,
    AGENCIA_GOV,
    EIXOS,
    FONTES,
)
from src.preparacao import esquema


class NavegadorFalso:
    """Substitui a rede: páginas em memória e robots.txt configurável."""

    def __init__(self, paginas: dict[str, str], proibidas: set[str] = frozenset()):
        self.paginas = paginas
        self.proibidas = proibidas
        self.baixadas: list[str] = []

    def pode_acessar(self, url):
        return url not in self.proibidas

    def baixar(self, url):
        self.baixadas.append(url)
        return self.paginas.get(url)


def test_extracao_agencia_gov(fixture):
    noticia = coletor.extrair_noticia(
        AGENCIA_GOV,
        fixture("agenciagov_noticia.html"),
        "/noticias/202607/gd-50-gw",
        "busca",
    )
    assert noticia["titulo"] == "Geração distribuída supera 50 GW no Brasil"
    assert noticia["data_publicacao"] == datetime(2026, 7, 23, 10, 15, 2)
    assert "A reprodução é gratuita" not in noticia["texto"]  # aviso descartado
    assert "Link:" not in noticia["texto"] and "rodapé" not in noticia["texto"]
    assert noticia["texto"].count("\n") == 1  # dois parágrafos de conteúdo
    assert noticia["ufs_mencionadas"] == "MA,PI,BA,SP"
    assert noticia["nivel_texto"] == esquema.NIVEL_INTEGRAL


def test_extracao_agencia_brasil_mantem_regra_do_tp2(fixture):
    noticia = coletor.extrair_noticia(
        AGENCIA_BRASIL,
        fixture("agenciabrasil_noticia.html"),
        "/geral/noticia/2026-07/usina",
        "energia-solar",
    )
    assert noticia["data_publicacao"] == datetime(2026, 7, 8, 19, 40)
    assert noticia["id"] == esquema.id_noticia(
        "https://agenciabrasil.ebc.com.br/geral/noticia/2026-07/usina"
    )


def test_listagem_prefiltra_e_respeita_dominio(fixture):
    url = AGENCIA_GOV.listagens[0].montar_url(0)
    fonte = type(AGENCIA_GOV)(
        **{**AGENCIA_GOV.__dict__, "listagens": AGENCIA_GOV.listagens[:1]}
    )
    contagem = Counter()
    links = coletor.coletar_links(
        fonte, NavegadorFalso({url: fixture("agenciagov_listagem.html")}), contagem
    )
    assert list(links) == ["/noticias/202607/geracao-distribuida-supera-50-gw"]
    assert contagem["descartadas_prefiltro"] == 2  # petróleo e bandeira tarifária


def test_robots_bloqueia_listagem(fixture):
    url = AGENCIA_GOV.listagens[0].montar_url(0)
    fonte = type(AGENCIA_GOV)(
        **{**AGENCIA_GOV.__dict__, "listagens": AGENCIA_GOV.listagens[:1]}
    )
    navegador = NavegadorFalso(
        {url: fixture("agenciagov_listagem.html")}, proibidas={url}
    )
    contagem = Counter()
    assert coletor.coletar_links(fonte, navegador, contagem) == {}
    assert navegador.baixadas == [] and contagem["listagens_bloqueadas"] == 1


def test_coleta_html_usa_cache_e_pula_existentes(fixture, tmp_path, monkeypatch):
    monkeypatch.setattr(coletor, "PASTA_CACHE", tmp_path)
    listagem = AGENCIA_GOV.listagens[0].montar_url(0)
    materia = (
        "https://agenciagov.ebc.com.br/noticias/202607/geracao-distribuida-supera-50-gw"
    )
    fonte = type(AGENCIA_GOV)(
        **{**AGENCIA_GOV.__dict__, "listagens": AGENCIA_GOV.listagens[:1]}
    )
    navegador = NavegadorFalso(
        {
            listagem: fixture("agenciagov_listagem.html"),
            materia: fixture("agenciagov_noticia.html"),
        }
    )

    registros, contagem = coletor.coletar_fonte_html(
        fonte, navegador, set(), reprocessar=False
    )
    assert len(registros) == 1 and contagem["baixadas"] == 1
    assert (
        tmp_path / "agenciagov" / "202607_geracao-distribuida-supera-50-gw.html"
    ).exists()

    _, contagem = coletor.coletar_fonte_html(
        fonte, navegador, {registros[0]["id"]}, reprocessar=False
    )
    assert contagem["ja_no_corpus"] == 1 and navegador.baixadas.count(materia) == 1


def test_rss_guarda_apenas_metadados(fixture):
    registros, contagem = coletor.extrair_itens_rss(
        EIXOS, fixture("eixos_feed.xml"), "rss:/solar/feed/"
    )
    assert len(registros) == 1 and contagem["irrelevantes"] == 1
    noticia = registros[0]
    assert (
        noticia["texto"] is None and noticia["nivel_texto"] == esquema.NIVEL_METADADOS
    )
    assert "TEXTO INTEGRAL" not in str(noticia)  # content:encoded ignorado
    assert noticia["ufs_mencionadas"] == "MG,PR"
    assert noticia["data_publicacao"] == datetime(2024, 8, 8, 10, 0)  # UTC -> Brasília


def test_eixos_desabilitada_por_padrao():
    assert not EIXOS.habilitada and EIXOS.nivel_texto == esquema.NIVEL_METADADOS
    assert all(f.nivel_texto == esquema.NIVEL_INTEGRAL for f in FONTES if f.habilitada)


def _registro(id_, titulo, nivel=esquema.NIVEL_INTEGRAL, resumo=None):
    return {
        "id": id_,
        "fonte": "F",
        "url": f"https://x/{id_}",
        "data_publicacao": pd.Timestamp("2026-01-01"),
        "titulo": titulo,
        "linha_fina": None,
        "texto": "t",
        "ufs_mencionadas": "",
        "nivel_texto": nivel,
        "tag_origem": "t",
        "coletado_em": pd.Timestamp("2026-01-02"),
        "resumo": resumo,
        "sentimento": None,
    }


def test_mescla_preserva_saidas_do_modelo_e_remove_duplicadas():
    existente = pd.DataFrame(
        [_registro("a", "Energia solar cresce", resumo="resumo do LLM")]
    )
    novos = [
        {**_registro("a", "Energia solar cresce"), "texto": "versão reprocessada"},
        _registro(
            "b", "Energia Solar CRESCE!", nivel=esquema.NIVEL_METADADOS
        ),  # mesma notícia, outra fonte
        _registro("c", "Outra notícia de GD"),
    ]
    corpus, estatisticas = coletor.mesclar_corpus(existente, novos, reprocessar=True)
    assert set(corpus["id"]) == {"a", "c"}
    linha_a = corpus.set_index("id").loc["a"]
    assert (
        linha_a["texto"] == "versão reprocessada"
        and linha_a["resumo"] == "resumo do LLM"
    )
    assert estatisticas["duplicadas_entre_fontes"] == 1


def test_mescla_sem_reprocessar_nao_altera_existentes():
    existente = pd.DataFrame([_registro("a", "Energia solar cresce")])
    corpus, _ = coletor.mesclar_corpus(
        existente, [{**_registro("a", "Energia solar cresce"), "texto": "novo"}]
    )
    assert corpus.set_index("id").loc["a", "texto"] == "t"


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("2026-07-23T10:15:02-03:00", datetime(2026, 7, 23, 10, 15, 2)),
        ("08/07/2026 19:40", datetime(2026, 7, 8, 19, 40)),
        ("Tue, 21 Oct 2026 13:00:00 +0000", datetime(2026, 10, 21, 10, 0)),
        ("sem data", None),
    ],
)
def test_converter_data(valor, esperado):
    assert converter_data(valor) == esperado


def test_normalizar_titulo():
    assert normalizar_titulo("Geração Distribuída: 50 GW!") == normalizar_titulo(
        "geracao distribuida 50 gw"
    )
