"""robots.txt (RFC 9309, via protego), filtro de relevância da coleta e sitemap.

Os robots.txt reais das duas agências (baixados em 20/11/2026) estão em
tests/fixtures/robots_agenciabrasil.txt e robots_agenciagov.txt.
"""

from __future__ import annotations

import gzip
from collections import Counter
from urllib.robotparser import RobotFileParser

import pytest

from src.data_acquisition.noticias import coletor
from src.data_acquisition.noticias.base import (
    USER_AGENT,
    Navegador,
    eh_relevante,
    interpretar_robots,
)
from src.data_acquisition.noticias.fontes import AGENCIA_BRASIL, AGENCIA_GOV

AG = "https://agenciagov.ebc.com.br"
AB = "https://agenciabrasil.ebc.com.br"
BUSCA_AG = f"{AG}/@@search?SearchableText=energia+solar&b_start:int=0"


@pytest.fixture
def robots_ag(fixture):
    return interpretar_robots(200, fixture("robots_agenciagov.txt"))


@pytest.fixture
def robots_ab(fixture):
    return interpretar_robots(200, fixture("robots_agenciabrasil.txt"))


# ── Agência Gov ──


def test_agencia_gov_curinga_bloqueia_busca(robots_ag):
    assert not robots_ag.can_fetch(BUSCA_AG, USER_AGENT)
    assert not robots_ag.can_fetch(f"{AG}/noticias/energia?b_start:int=10", USER_AGENT)


def test_agencia_gov_materia_editoria_e_sitemap_permitidos(robots_ag):
    for caminho in (
        "/noticias/202607/aneel-multa-neoenergia-coelba",
        "/noticias/energia",
        "/sitemap.xml.gz",
    ):
        assert robots_ag.can_fetch(AG + caminho, USER_AGENT), caminho


def test_urllib_nao_entende_curinga_motivo_da_troca(fixture):
    """Documenta o defeito corrigido: o parser da biblioteca padrão liberava a busca."""
    antigo = RobotFileParser()
    antigo.parse(fixture("robots_agenciagov.txt").splitlines())
    assert antigo.can_fetch(USER_AGENT, BUSCA_AG)  # errado, por isso o protego


# ── Agência Brasil ──


def test_agencia_brasil_search_bloqueado(robots_ab):
    assert not robots_ab.can_fetch(f"{AB}/search/node?keys=fio+b", USER_AGENT)
    assert not robots_ab.can_fetch(f"{AB}/admin/", USER_AGENT)


def test_agencia_brasil_tags_paginadas_e_materias_permitidas(robots_ab):
    assert robots_ab.can_fetch(f"{AB}/tags/energia-solar", USER_AGENT)
    assert robots_ab.can_fetch(f"{AB}/tags/energia-solar?page=3", USER_AGENT)
    assert robots_ab.can_fetch(f"{AB}/economia/noticia/2026-07/usina-solar", USER_AGENT)


def test_crawl_delay(robots_ab, robots_ag):
    assert robots_ab.crawl_delay(USER_AGENT) == 10
    assert robots_ag.crawl_delay(USER_AGENT) is None


# ── Navegador com os robots.txt reais ──


class Resposta:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class SessaoFalsa:
    def __init__(self, respostas: dict[str, Resposta]):
        self.respostas = respostas
        self.headers: dict = {}

    def get(self, url, timeout=None):
        return self.respostas[url]


def test_navegador_aplica_robots_e_pausa(fixture):
    sessao = SessaoFalsa(
        {
            f"{AG}/robots.txt": Resposta(200, fixture("robots_agenciagov.txt")),
            f"{AB}/robots.txt": Resposta(200, fixture("robots_agenciabrasil.txt")),
        }
    )
    navegador = Navegador(sessao=sessao)
    assert navegador.diagnosticar(BUSCA_AG) == "proibido"
    assert navegador.diagnosticar(f"{AG}/noticias/202607/x") == "permitido"
    assert navegador.diagnosticar(f"{AB}/search/node") == "proibido"
    assert navegador.diagnosticar(f"{AB}/tags/energia-solar?page=2") == "permitido"
    assert navegador._pausa_para(f"{AB}/tags/x") == 10  # Crawl-delay maior que a pausa
    assert navegador._pausa_para(f"{AG}/noticias/x") == 1.5  # pausa padrão


def test_navegador_403_proibe_tudo_e_404_libera():
    sessao = SessaoFalsa(
        {
            "https://a.example/robots.txt": Resposta(403),
            "https://b.example/robots.txt": Resposta(404),
        }
    )
    navegador = Navegador(sessao=sessao)
    assert navegador.diagnosticar("https://a.example/qualquer") == "proibido"
    assert navegador.diagnosticar("https://b.example/qualquer") == "permitido"


# ── Filtro de relevância da coleta ──


@pytest.mark.parametrize(
    "texto",
    [
        "A Lei 14.300 mudou as regras",
        "a lei 14300 de 2022",
        "conforme a Lei nº 14.300/2022",
        "Lei Federal 14.300",
        "a cobrança do Fio B começou em 2023",
        "o fio b da tarifa",
        "o sistema de compensação de créditos da Aneel",
        "compensacao de creditos de energia",
        "modelo de net metering",
        "regras de net-metering",
        "a geração distribuída cresce",
        "geração própria distribuída",
        "microgeração em residências",
        "minigeração compartilhada",
        "micro e minigeração distribuída",
        "microgeradores e minigeradoras",
        "microgerações residenciais",
        "usina fotovoltaica",
        "energia solar",
    ],
)
def test_filtro_positivos(texto):
    assert eh_relevante(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "o fio branco do poste",  # "fio B" dentro de outra palavra
        "fio bom e barato",
        "a Lei 14.3001 não existe",
        "lei 143.00",
        "compensação de créditos de carbono no mercado regulado",
        "o GDF anunciou obras",  # "GD" dentro de sigla maior
        "a geração de empregos distribuída por setor",
        "microgerente de loja",  # prefixo sem o termo inteiro
        "Internet metering",  # "net metering" dentro de outra palavra
        "hidrelétrica do Tapajós",
    ],
)
def test_filtro_negativos(texto):
    assert not eh_relevante(texto)


# ── Sitemap ──

SITEMAP = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{AG}/noticias/202607/aneel-multa-coelba</loc></url>
  <url><loc>{AG}/noticias/202310/solar-no-semiarido</loc></url>
  <url><loc>{AG}/assuntos/energia</loc></url>
  <url><loc>https://outro.example/noticias/202607/x</loc></url>
</urlset>"""

INDICE = f"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>{AG}/sitemap-1.xml.gz</loc></sitemap>
</sitemapindex>"""


class NavegadorBytes:
    def __init__(self, conteudos: dict[str, bytes], proibidas: set[str] = frozenset()):
        self.conteudos = conteudos
        self.proibidas = proibidas

    def pode_acessar(self, url):
        return url not in self.proibidas

    def baixar_bytes(self, url):
        return self.conteudos.get(url)


def test_ler_sitemap_gz_e_xml():
    paginas, filhos = coletor.ler_sitemap(gzip.compress(SITEMAP.encode()))
    assert len(paginas) == 4 and filhos == []
    assert coletor.ler_sitemap(SITEMAP.encode())[0] == paginas
    assert coletor.ler_sitemap(INDICE.encode()) == ([], [f"{AG}/sitemap-1.xml.gz"])


def test_links_do_sitemap_filtra_dominio_e_padrao_e_segue_indice():
    navegador = NavegadorBytes(
        {
            f"{AG}/sitemap.xml.gz": gzip.compress(INDICE.encode()),
            f"{AG}/sitemap-1.xml.gz": gzip.compress(SITEMAP.encode()),
        }
    )
    caminhos = coletor.links_do_sitemap(
        AGENCIA_GOV, navegador, f"{AG}/sitemap.xml.gz", Counter()
    )
    assert caminhos == [
        "/noticias/202607/aneel-multa-coelba",
        "/noticias/202310/solar-no-semiarido",
    ]


def test_links_do_sitemap_respeita_robots():
    contagem = Counter()
    navegador = NavegadorBytes(
        {f"{AG}/sitemap.xml.gz": SITEMAP.encode()}, proibidas={f"{AG}/sitemap.xml.gz"}
    )
    assert (
        coletor.links_do_sitemap(
            AGENCIA_GOV, navegador, f"{AG}/sitemap.xml.gz", contagem
        )
        == []
    )
    assert contagem["listagens_bloqueadas"] == 1


def test_fontes_nao_usam_url_proibida(robots_ab, robots_ag):
    """Toda listagem e sitemap configurados são permitidos pelos robots.txt reais."""
    for fonte, robots in ((AGENCIA_BRASIL, robots_ab), (AGENCIA_GOV, robots_ag)):
        for listagem in fonte.listagens:
            for pagina in (0, 1):
                url = listagem.montar_url(pagina)
                assert robots.can_fetch(url, USER_AGENT), url
        for sitemap in fonte.sitemaps:
            assert robots.can_fetch(sitemap, USER_AGENT), sitemap


# ── Robustez a páginas que não são matéria ──


class RespostaHttp:
    def __init__(self, tipo: str, corpo: bytes = b"<html></html>"):
        self.status_code = 200
        self.headers = {"Content-Type": tipo}
        self.content = corpo
        self.text = corpo.decode("latin-1")
        self.apparent_encoding = "utf-8"
        self.encoding = None

    def raise_for_status(self):
        return None


def test_baixar_ignora_conteudo_nao_textual(monkeypatch):
    navegador = Navegador(pausa=0)
    monkeypatch.setattr(
        navegador, "_obter", lambda url: RespostaHttp("video/mp4", b"\x00ftypmp42")
    )
    assert navegador.baixar(f"{AG}/noticias/202310/video") is None
    monkeypatch.setattr(
        navegador, "_obter", lambda url: RespostaHttp("text/html; charset=utf-8")
    )
    assert navegador.baixar(f"{AG}/noticias/202310/materia") == "<html></html>"


def test_pagina_que_quebra_a_extracao_nao_derruba_a_fonte(monkeypatch, tmp_path):
    monkeypatch.setattr(coletor, "PASTA_CACHE", tmp_path)
    fonte = type(AGENCIA_GOV)(**{**AGENCIA_GOV.__dict__, "sitemaps": ()})
    monkeypatch.setattr(
        coletor, "coletar_links", lambda *a: {"/noticias/202310/ruim": "sitemap"}
    )
    monkeypatch.setattr(coletor, "obter_html", lambda *a: "<html>")

    def quebra(*args):
        raise AssertionError("expected name token")

    monkeypatch.setattr(coletor, "extrair_noticia", quebra)
    registros, contagem = coletor.coletar_fonte_html(fonte, None, set(), False)
    assert registros == [] and contagem["falha_extracao"] == 1
