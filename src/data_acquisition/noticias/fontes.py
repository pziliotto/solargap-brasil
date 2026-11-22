"""
PROJETO: SolarGap Brasil
ARQUIVO: noticias/fontes.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Cadastro das fontes de notícias avaliadas no TP3, com licença, nível de
    texto e justificativa. Adicionar uma fonte = adicionar uma entrada aqui.

CRITÉRIOS DE AVALIAÇÃO (nesta ordem):
    1. Acesso liberado — sem paywall para o conteúdo;
    2. Termos de uso — a reprodução é autorizada? A coleta automatizada é
       proibida? O repositório do projeto é PÚBLICO: copiar texto sem
       autorização seria redistribuir conteúdo protegido;
    3. robots.txt — verificado em toda execução, por URL (Navegador);
    4. Estrutura — HTML estático (BeautifulSoup basta) ou dinâmico (Selenium).

NÍVEL DE TEXTO PROPORCIONAL À LICENÇA:
    integral   — licença autoriza reprodução com citação: guarda o texto todo
    metadados  — sem autorização de cópia: só título, linha fina, data e link,
                 lidos do feed RSS que o próprio veículo publica para leitores
                 automáticos. Nenhuma página de matéria é baixada nem guardada.

RESULTADO DA AVALIAÇÃO (outubro/2026):
    Agência Brasil  habilitada  integral   "reprodução autorizada mediante indicação da fonte"
    Agência Gov     habilitada  integral   página informa: "A reprodução é gratuita desde que
                                           citada a fonte". Republica os boletins mensais da
                                           ANEEL sobre MMGD, com dados por estado
    eixos (epbr)    DESABILITADA metadados termos restringem a uso pessoal e proíbem copiar,
                                           baixar ou manter cache sem autorização por escrito.
                                           Habilitar só após autorização (contato no rodapé)
    ANEEL e MME     habilitadas integral   (20/11/2026) gov.br sob CC BY-ND 3.0: reprodução
                                           literal com atribuição. Descoberta: sitemap (ANEEL)
                                           e listagem paginada permitida (MME, sem sitemap)
    Demais veículos: ver NAO_INCLUIDAS, ao fim do arquivo.

SELENIUM:
    Nenhuma fonte viável exige renderização por JavaScript: listagens, matérias
    e feeds chegam completos no HTML/XML. Na ANEEL (Plone Volto), o corpo vem
    como JSON embutido no HTML (window.__data), lido sem executar JavaScript. Seguindo a orientação do enunciado
    ("mantenha a simplicidade quando possível"), o projeto não usa Selenium.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from src.preparacao import esquema


@dataclass(frozen=True)
class Listagem:
    """Página (ou sequência de páginas) que lista links de notícias."""

    rotulo: str
    montar_url: Callable[[int], str]  # número da página (0, 1, 2...) -> URL
    max_paginas: int = 10
    prefiltrar_titulo: bool = (
        False  # listagem genérica: só segue links com título relevante
    )


@dataclass(frozen=True)
class Fonte:
    chave: str
    nome: str
    base: str
    licenca: str
    termos_url: str
    nivel_texto: str
    habilitada: bool
    motivo: str
    tipo: str = "html"  # "html" (listagem + matéria) ou "rss" (só feed)
    listagens: tuple[Listagem, ...] = ()
    sitemaps: tuple[str, ...] = ()  # sitemap.xml(.gz) indicado no robots.txt da fonte
    feeds: tuple[str, ...] = ()
    padrao_link: re.Pattern | None = None
    padrao_data_texto: re.Pattern | None = None
    descartar_paragrafos: tuple[re.Pattern, ...] = field(default_factory=tuple)


# ═══════════════════ Agência Brasil (EBC) ═══════════════════

BASE_AGENCIA_BRASIL = "https://agenciabrasil.ebc.com.br"
TAGS_AGENCIA_BRASIL = [
    "energia-solar-1",
    "energia-solar",
    "geracao-distribuida",
    "energia-renovavel",
    "energias-renovaveis",
    # Tarefa 5a (20/11/2026): tags que existem no portal para as palavras-chave
    # do benchmark v2. Não existem: lei-14300 (e variações), microgeracao,
    # micro-e-minigeracao, compensacao-de-energia (e variações) e fio-b.
    "micro-geracao",
    "minigeracao",
    "fotovoltaica",
    "energia-fotovoltaica",
    "paineis-solares",
    "placas-solares",
    "net-metering",
    "geracao-de-energia-solar",
    "usina-solar",
    "usinas-solares",
]


def _url_tag_agencia_brasil(tag: str) -> Callable[[int], str]:
    return lambda pagina: (
        f"{BASE_AGENCIA_BRASIL}/tags/{tag}" + (f"?page={pagina}" if pagina else "")
    )


AGENCIA_BRASIL = Fonte(
    chave="agenciabrasil",
    nome="Agência Brasil",
    base=BASE_AGENCIA_BRASIL,
    licenca="EBC: reprodução autorizada mediante indicação da fonte, sem finalidade comercial",
    termos_url="https://www.ebc.com.br/termos-de-uso-e-condicoes-gerais-do-portal-da-ebc",
    nivel_texto=esquema.NIVEL_INTEGRAL,
    habilitada=True,
    motivo="Fonte do TP2. Licença autoriza reprodução com citação.",
    listagens=tuple(
        Listagem(tag, _url_tag_agencia_brasil(tag)) for tag in TAGS_AGENCIA_BRASIL
    ),
    padrao_link=re.compile(r"^/[a-z-]+/noticia/\d{4}-\d{2}/[\w-]+$"),
    padrao_data_texto=re.compile(
        r"Publicado em\s+(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}:\d{2})"
    ),
)

# ═══════════════════ Agência Gov (EBC) ═══════════════════

BASE_AGENCIA_GOV = "https://agenciagov.ebc.com.br"
# A busca interna (/@@search?SearchableText=...) NÃO é usada: o robots.txt da
# Agência Gov proíbe toda URL com "?" (Disallow: /*?). Até 20/11/2026 o parser
# do projeto não entendia curingas e a liberava; ver Data Summary Report, 2.3.
# As matérias são descobertas pelo sitemap que o próprio robots.txt indica.


AGENCIA_GOV = Fonte(
    chave="agenciagov",
    nome="Agência Gov",
    base=BASE_AGENCIA_GOV,
    licenca="EBC: 'A reprodução é gratuita desde que citada a fonte' (aviso em cada matéria)",
    termos_url="https://www.ebc.com.br/termos-de-uso-e-condicoes-gerais-do-portal-da-ebc",
    nivel_texto=esquema.NIVEL_INTEGRAL,
    habilitada=True,
    motivo="Nova no TP3. Notícias do governo federal, incluindo os boletins mensais da ANEEL sobre MMGD.",
    listagens=(
        # Editoria Energia: ampla (petróleo, mineração...), por isso o pré-filtro pelo título.
        Listagem(
            "editoria:energia",
            lambda pagina: f"{BASE_AGENCIA_GOV}/noticias/energia",
            max_paginas=1,
            prefiltrar_titulo=True,
        ),
    ),
    sitemaps=(f"{BASE_AGENCIA_GOV}/sitemap.xml.gz",),
    padrao_link=re.compile(r"^/noticias/\d{6}/[\w-]+$"),
    descartar_paragrafos=(
        re.compile(r"^A reprodução é gratuita", re.IGNORECASE),
        re.compile(r"^Link:\s*https?://", re.IGNORECASE),
        re.compile(r"^Leia mais", re.IGNORECASE),
    ),
)

# ═══════════════════ ANEEL e MME (gov.br) ═══════════════════
# Avaliação de 20/11/2026 (Data Summary Report, 2.4):
#   acesso livre; rodapé de todo o gov.br: "Todo o conteúdo deste site está
#   publicado sob a licença Creative Commons Atribuição-SemDerivações 3.0 Não
#   Adaptada" (reprodução literal com atribuição); os Termos de Uso do gov.br
#   não proíbem coleta automatizada; robots.txt de www.gov.br sem regras para
#   /aneel e /mme e sem Crawl-delay (vale a pausa padrão de 1,5 s).

BASE_GOV_BR = "https://www.gov.br"
LICENCA_GOV_BR = "gov.br: Creative Commons Atribuição-SemDerivações 3.0 (CC BY-ND 3.0)"
TERMOS_GOV_BR = "https://www.gov.br/pt-br/termos-de-uso"
_NAO_MATERIA = r"(?![\w.-]+\.(?:jpe?g|png|gif|webp|pdf)$)"  # anexos no mesmo caminho

ANEEL = Fonte(
    chave="aneel",
    nome="ANEEL",
    base=BASE_GOV_BR,
    licenca=LICENCA_GOV_BR,
    termos_url=TERMOS_GOV_BR,
    nivel_texto=esquema.NIVEL_INTEGRAL,
    habilitada=True,
    motivo=(
        "Nova na Tarefa 5a. Regulador da geração distribuída: notícias sobre Lei 14.300, "
        "MMGD e compensação de energia. Site Plone Volto: a listagem é montada por "
        "JavaScript, por isso a descoberta é pelo sitemap do órgão."
    ),
    sitemaps=(f"{BASE_GOV_BR}/aneel/sitemap.xml.gz",),
    padrao_link=re.compile(
        rf"^/aneel/pt-br/assuntos/noticias/\d{{4}}/{_NAO_MATERIA}[\w.-]+$"
    ),
    padrao_data_texto=re.compile(
        r"Publicado em\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}[:h]\d{2})"
    ),
)

MME = Fonte(
    chave="mme",
    nome="MME",
    base=BASE_GOV_BR,
    licenca=LICENCA_GOV_BR,
    termos_url=TERMOS_GOV_BR,
    nivel_texto=esquema.NIVEL_INTEGRAL,
    habilitada=True,
    motivo=(
        "Nova na Tarefa 5a. O MME não publica sitemap (404); a listagem de notícias é "
        "permitida pelo robots.txt, inclusive a paginação. É ampla (petróleo, gás, "
        "mineração), por isso o pré-filtro pelo título."
    ),
    listagens=(
        Listagem(
            "noticias",
            lambda pagina: (
                f"{BASE_GOV_BR}/mme/pt-br/assuntos/noticias"
                + (f"?b_start:int={30 * pagina}" if pagina else "")
            ),
            max_paginas=250,
            prefiltrar_titulo=True,
        ),
    ),
    padrao_link=re.compile(
        rf"^/mme/pt-br/assuntos/noticias/(?:[\w-]+/)?{_NAO_MATERIA}[\w.-]+$"
    ),
    padrao_data_texto=re.compile(
        r"Publicado em\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}[:h]\d{2})"
    ),
    descartar_paragrafos=(  # contato da assessoria e redes sociais, ao fim das matérias
        re.compile(r"^Assessoria (?:Especial )?de Comunica", re.IGNORECASE),
        re.compile(r"^Instagram\s*●", re.IGNORECASE),
        re.compile(r"^ascom@mme\.gov\.br", re.IGNORECASE),
        re.compile(r"^Ministério de Minas e Energia \(61\)", re.IGNORECASE),
    ),
)

# ═══════════════════ eixos, ex-epbr (somente metadados) ═══════════════════

EIXOS = Fonte(
    chave="eixos",
    nome="eixos",
    base="https://eixos.com.br",
    licenca="Todos os direitos reservados; termos permitem só uso pessoal e não comercial",
    termos_url="https://eixos.com.br/termos-de-uso/",
    nivel_texto=esquema.NIVEL_METADADOS,
    habilitada=False,
    motivo=(
        "Termos de uso proíbem copiar, baixar ou manter cache do conteúdo sem autorização por "
        "escrito. Habilitar (habilitada=True) somente após autorização da agência."
    ),
    tipo="rss",
    feeds=(
        "https://eixos.com.br/solar/feed/",  # categoria Energia Solar (WordPress)
        "https://eixos.com.br/tag/geracao-distribuida/feed/",
    ),
)

FONTES: tuple[Fonte, ...] = (AGENCIA_BRASIL, AGENCIA_GOV, ANEEL, MME, EIXOS)
FONTES_POR_CHAVE = {fonte.chave: fonte for fonte in FONTES}

# ═══════════════════ Avaliadas e não incluídas ═══════════════════

NAO_INCLUIDAS = {
    "g1 / Globo": (
        "Termos gerais da Globo autorizam indexação automatizada apenas por buscadores "
        "públicos, para exibir links. Outra coleta automatizada não é autorizada."
    ),
    "CNN Brasil": "Termos de uso não localizados na avaliação; conteúdo com todos os direitos reservados.",
    "Portal R7": "Termos de uso não localizados na avaliação; conteúdo com todos os direitos reservados.",
    "CanalEnergia": "Modelo de assinatura: o conteúdo não é de acesso liberado.",
    "MegaWhat": "Modelo de assinatura: o conteúdo não é de acesso liberado.",
    "Canal Solar": "Pede contato prévio para reutilização do material.",
}
