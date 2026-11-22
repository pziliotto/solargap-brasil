"""Fontes ANEEL e MME (gov.br): robots.txt, padrões de link, Volto e paginação.

O robots.txt real de www.gov.br (baixado em 20/11/2026) está em
tests/fixtures/robots_govbr.txt.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from src.data_acquisition.noticias import coletor
from src.data_acquisition.noticias.base import (
    USER_AGENT,
    extrair_volto,
    interpretar_robots,
)
from src.data_acquisition.noticias.fontes import ANEEL, MME, Fonte, Listagem

GOV = "https://www.gov.br"


@pytest.fixture
def robots_gov(fixture):
    return interpretar_robots(200, fixture("robots_govbr.txt"))


def test_robots_govbr_permite_sitemap_materias_e_paginacao(robots_gov):
    for url in (
        f"{GOV}/aneel/sitemap.xml.gz",
        f"{GOV}/aneel/sitemap1.xml.gz",
        f"{GOV}/aneel/pt-br/assuntos/noticias/2026/aneel-aprova-regras",
        f"{GOV}/mme/pt-br/assuntos/noticias?b_start:int=30",
        f"{GOV}/mme/pt-br/assuntos/noticias/novembro-26/leilao",
    ):
        assert robots_gov.can_fetch(url, USER_AGENT), url
    assert robots_gov.crawl_delay(USER_AGENT) is None  # vale a pausa padrão de 1,5 s


def test_robots_govbr_mantem_bloqueios_de_outros_orgaos(robots_gov):
    assert not robots_gov.can_fetch(f"{GOV}/mre/pt-br/busca?x=1", USER_AGENT)
    assert not robots_gov.can_fetch(f"{GOV}/aneel/pt-br/sendto_form", USER_AGENT)


def test_fontes_govbr_nao_usam_url_proibida(robots_gov):
    for fonte in (ANEEL, MME):
        for listagem in fonte.listagens:
            for pagina in (0, 1, 194):
                assert robots_gov.can_fetch(listagem.montar_url(pagina), USER_AGENT)
        for sitemap in fonte.sitemaps:
            assert robots_gov.can_fetch(sitemap, USER_AGENT)


@pytest.mark.parametrize(
    ("fonte", "caminho", "aceito"),
    [
        (ANEEL, "/aneel/pt-br/assuntos/noticias/2026/aneel-aprova-regras-de-gd", True),
        (ANEEL, "/aneel/pt-br/assuntos/noticias/2026/lote-6-e-da-cox-brasil-s.a", True),
        (ANEEL, "/aneel/pt-br/assuntos/noticias/2026/foto-da-usina.jpg", False),
        (ANEEL, "/aneel/pt-br/assuntos/noticias/2026/nota-tecnica.pdf", False),
        (ANEEL, "/aneel/pt-br/assuntos/noticias/2026", False),
        (ANEEL, "/aneel/pt-br/assuntos/noticias/2026/materia/imagem", False),
        (MME, "/mme/pt-br/assuntos/noticias/novembro-26/leilao-de-energia", True),
        (MME, "/mme/pt-br/assuntos/noticias/mme-e-india-avancam", True),
        (MME, "/mme/pt-br/assuntos/noticias/novembro-26/grafico.png", False),
        (MME, "/aneel/pt-br/assuntos/noticias/2026/x", False),
    ],
)
def test_padrao_link_govbr(fonte, caminho, aceito):
    assert bool(fonte.padrao_link.match(caminho)) is aceito


# ── Plone Volto (ANEEL) ──


def pagina_volto(blocos: dict, ordem: list[str]) -> str:
    dados = {
        "router": {"location": {"state": "__UNDEF__"}},
        "content": {
            "data": {
                "effective": "2026-09-01T22:04:07+00:00",
                "created": "2026-09-01T22:03:58+00:00",
                "blocks": blocos,
                "blocks_layout": {"items": ordem},
            }
        },
    }
    objeto = json.dumps(dados).replace('"__UNDEF__"', "undefined")  # é JS, não JSON
    return (
        "<html><head><meta property='og:title' content='ANEEL aprova regras'></head>"
        "<body><p class='documentDescription'>Linha fina curta.</p>"
        f"<script>window.__data={objeto};</script></body></html>"
    )


PARAGRAFO = "A Diretoria da ANEEL aprovou nesta terça as novas regras de compensação."


def test_extrair_volto_le_blocos_na_ordem_e_data():
    html = pagina_volto(
        {
            "b": {"@type": "html", "html": f"<p>{PARAGRAFO}</p><p>curto</p>"},
            "a": {"@type": "title"},
            "c": {
                "@type": "slate",
                "plaintext": "Segundo parágrafo, escrito no editor slate.",
            },
            "d": {
                "@type": "text",
                "text": {
                    "blocks": [
                        {"text": "Terceiro parágrafo, do editor draft-js antigo."}
                    ]
                },
            },
        },
        ordem=["a", "b", "c", "d"],
    )
    texto, data = extrair_volto(html)
    assert texto.split("\n") == [
        PARAGRAFO,
        "Segundo parágrafo, escrito no editor slate.",
        "Terceiro parágrafo, do editor draft-js antigo.",
    ]
    assert data.isoformat() == "2026-09-01T19:04:07"  # convertido para Brasília


def test_extrair_volto_fora_do_volto_e_json_quebrado():
    assert extrair_volto("<html><p>página comum</p></html>") == ("", None)
    assert extrair_volto("<script>window.__data={quebrado</script>") == ("", None)


def test_extrair_noticia_prefere_corpo_volto():
    html = pagina_volto({"b": {"@type": "html", "html": f"<p>{PARAGRAFO}</p>"}}, ["b"])
    noticia = coletor.extrair_noticia(
        ANEEL, html, "/aneel/pt-br/assuntos/noticias/2026/x", "sitemap"
    )
    assert noticia["texto"] == PARAGRAFO
    assert noticia["titulo"] == "ANEEL aprova regras"
    assert str(noticia["data_publicacao"]) == "2026-09-01 19:04:07"


# ── Paginação com pré-filtro de título (MME) ──


class NavegadorListagem:
    def __init__(self, paginas: dict[str, str]):
        self.paginas = paginas

    def pode_acessar(self, url):
        return True

    def baixar(self, url):
        return self.paginas.get(url)


def test_paginacao_continua_quando_pagina_nao_tem_titulo_relevante():
    """Antes, uma página sem títulos relevantes encerrava a paginação."""
    base = f"{GOV}/mme/pt-br/assuntos/noticias"

    def ancora(slug, titulo):
        return f"<a href='{base}/{slug}'>{titulo}</a>"

    paginas = {
        base: ancora("petroleo", "Leilão de petróleo"),
        f"{base}?b_start:int=30": ancora("gas", "Gás do Povo"),
        f"{base}?b_start:int=60": ancora("gd", "Regras da geração distribuída"),
    }
    fonte = Fonte(
        **{
            **MME.__dict__,
            "listagens": (
                Listagem(
                    "noticias",
                    MME.listagens[0].montar_url,
                    max_paginas=10,
                    prefiltrar_titulo=True,
                ),
            ),
        }
    )
    contagem = Counter()
    links = coletor.coletar_links(fonte, NavegadorListagem(paginas), contagem)
    assert links == {"/mme/pt-br/assuntos/noticias/gd": "noticias"}
    assert contagem["descartadas_prefiltro"] == 2


def test_caminho_cache_encurta_slug_longo_sem_colidir(tmp_path):
    slug = "consumidores-pagarao-" + "x" * 250
    a = coletor.caminho_cache(
        ANEEL, f"/aneel/pt-br/assuntos/noticias/2022/{slug}", tmp_path
    )
    b = coletor.caminho_cache(
        ANEEL, f"/aneel/pt-br/assuntos/noticias/2023/{slug}", tmp_path
    )
    assert len(a.name) <= coletor.LIMITE_NOME_CACHE + len(".html")
    assert a != b and a.name.startswith("2022_consumidores-pagarao-")
    curto = coletor.caminho_cache(
        ANEEL, "/aneel/pt-br/assuntos/noticias/2026/curta", tmp_path
    )
    assert curto.name == "2026_curta.html"  # nomes curtos (cache existente) não mudam


@pytest.mark.parametrize(
    "paragrafo",
    [
        "Assessoria de Comunicação Social Ministério de Minas e Energia (61) 2032-5620",
        "Assessoria Especial de Comunicação Social - MME Telefone : (61) 2032-5759",
        "Instagram ● Twitter ● Facebook ● YouTube ● Flickr ● LinkedIn",
        "ascom@mme.gov.br antigo.mme.gov.br www.twitter.com/Minas_Energia",
        "Ministério de Minas e Energia (61) 2032-5620 ascom@mme.gov.br",
    ],
)
def test_mme_descarta_rodape_da_assessoria(paragrafo):
    assert any(p.search(paragrafo) for p in MME.descartar_paragrafos)
