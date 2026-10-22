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
    Demais veículos: ver NAO_INCLUIDAS, ao fim do arquivo.

SELENIUM:
    Nenhuma fonte viável exige renderização por JavaScript: listagens, matérias
    e feeds chegam completos no HTML/XML. Seguindo a orientação do enunciado
    ("mantenha a simplicidade quando possível"), o projeto não usa Selenium.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import quote_plus

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
TERMOS_BUSCA_AGENCIA_GOV = [
    "energia solar",
    "geração distribuída",
    "micro e minigeração",
    "fotovoltaica",
]
TAMANHO_LOTE_PLONE = 10  # resultados por página na busca do Plone (b_start)


def _url_busca_agencia_gov(termo: str) -> Callable[[int], str]:
    return lambda pagina: (
        f"{BASE_AGENCIA_GOV}/@@search?SearchableText={quote_plus(termo)}"
        f"&b_start:int={pagina * TAMANHO_LOTE_PLONE}"
    )


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
        *(
            Listagem(f"busca:{termo}", _url_busca_agencia_gov(termo))
            for termo in TERMOS_BUSCA_AGENCIA_GOV
        ),
    ),
    padrao_link=re.compile(r"^/noticias/\d{6}/[\w-]+$"),
    descartar_paragrafos=(
        re.compile(r"^A reprodução é gratuita", re.IGNORECASE),
        re.compile(r"^Link:\s*https?://", re.IGNORECASE),
        re.compile(r"^Leia mais", re.IGNORECASE),
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

FONTES: tuple[Fonte, ...] = (AGENCIA_BRASIL, AGENCIA_GOV, EIXOS)
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
