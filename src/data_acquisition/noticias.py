"""
PROJETO: SolarGap Brasil
ARQUIVO: noticias.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 20/09/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Coleta notícias sobre energia solar e geração distribuída da Agência Brasil
    (EBC) via web scraping estático com BeautifulSoup. O corpus alimenta a
    nuvem de palavras e as estatísticas de texto do dashboard (TP2) e será
    processado por modelo de linguagem local no TP4.

FONTE:
    Agência Brasil — páginas de tag (HTML estático, paginação ?page=N).

LICENCIAMENTO:
    Termos de uso da EBC: reprodução autorizada mediante indicação da fonte,
    para uso sem finalidade comercial. Cada registro guarda a URL de origem.

BOAS PRÁTICAS DE COLETA:
    - robots.txt consultado antes de cada requisição;
    - User-Agent identificado como projeto acadêmico;
    - pausa entre requisições;
    - HTML bruto salvo em cache (data/raw/html/): uma notícia já baixada
      nunca é requisitada de novo.

EXTRAÇÃO:
    Não depende de classes CSS do site, que mudam com frequência:
        - links de notícia: padrão de URL /<editoria>/noticia/AAAA-MM/<slug>;
        - data: texto "Publicado em DD/MM/AAAA - HH:MM";
        - corpo: o elemento com maior volume de texto em parágrafos <p>.

SAÍDA:
    data/processed/corpus_noticias.csv
    As colunas resumo e sentimento ficam vazias: serão preenchidas pelo
    modelo de linguagem no TP4, sem alteração de esquema.

OBS. DE USO:
    Rodar como módulo a partir da raiz:
        python -m src.data_acquisition.noticias
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.data_acquisition.coletor_base import (
    calcular_espera_backoff,
    configurar_logging,
    obter_project_root,
)
from src.preparacao import esquema

PROJECT_ROOT = obter_project_root(__file__)
PASTA_CACHE = PROJECT_ROOT / "data" / "raw" / "html" / "agenciabrasil"
PASTA_PROCESSED = PROJECT_ROOT / "data" / "processed"
PASTA_LOGS = PROJECT_ROOT / "logs"
SAIDA_CORPUS = PASTA_PROCESSED / "corpus_noticias.csv"

BASE = "https://agenciabrasil.ebc.com.br"
FONTE = "Agência Brasil"
USER_AGENT = "SolarGapBrasil/1.0 (projeto academico de ciencia de dados; INFNET)"

# Tags inexistentes são registradas no log e ignoradas.
TAGS = [
    "energia-solar-1",
    "energia-solar",
    "geracao-distribuida",
    "energia-renovavel",
    "energias-renovaveis",
]
MAX_PAGINAS_POR_TAG = 10
PAUSA_SEGUNDOS = 1.5
TENTATIVAS = 3
SEPARADOR = ";"

PADRAO_NOTICIA = re.compile(r"^/[a-z-]+/noticia/\d{4}-\d{2}/[\w-]+$")
PADRAO_DATA = re.compile(r"Publicado em\s+(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}:\d{2})")
PADRAO_RELEVANCIA = re.compile(
    r"solar|fotovolt|gera[çc][ãa]o\s+distribu[íi]da|\bGD\b", re.IGNORECASE
)
TAMANHO_MINIMO_PARAGRAFO = 40


# ═══════════════════ Rede ═══════════════════


def carregar_robots() -> RobotFileParser:
    robots = RobotFileParser(f"{BASE}/robots.txt")
    try:
        robots.read()
    except Exception as erro:  # noqa: BLE001 — sem robots legível, não coleta
        logging.error("Não foi possível ler o robots.txt: %s", erro)
        sys.exit(1)
    logging.info("robots.txt carregado.")
    return robots


def baixar(sessao: requests.Session, url: str) -> str | None:
    """GET com retry e backoff. Devolve None para 404 ou falha persistente."""
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resposta = sessao.get(url, timeout=30)
            time.sleep(PAUSA_SEGUNDOS)

            if resposta.status_code == 404:
                logging.warning("Página inexistente (404): %s", url)
                return None

            resposta.raise_for_status()
            resposta.encoding = resposta.apparent_encoding or "utf-8"
            return resposta.text

        except requests.exceptions.RequestException as erro:
            logging.warning(
                "Falha na tentativa %d/%d (%s): %s", tentativa, TENTATIVAS, url, erro
            )
            if tentativa < TENTATIVAS:
                time.sleep(calcular_espera_backoff(tentativa, 2))

    logging.error("Desistindo após %d tentativas: %s", TENTATIVAS, url)
    return None


def caminho_cache(caminho_url: str) -> Path:
    """/economia/noticia/2023-08/slug -> 2023-08_slug.html"""
    partes = caminho_url.strip("/").split("/")
    return PASTA_CACHE / f"{partes[-2]}_{partes[-1]}.html"


def obter_html_noticia(
    sessao: requests.Session,
    robots: RobotFileParser,
    caminho_url: str,
    contagem: Counter,
) -> str | None:
    arquivo = caminho_cache(caminho_url)
    if arquivo.exists():
        contagem["cache"] += 1
        return arquivo.read_text(encoding="utf-8")

    url = urljoin(BASE, caminho_url)
    if not robots.can_fetch(USER_AGENT, url):
        logging.warning("Bloqueado pelo robots.txt: %s", url)
        contagem["bloqueadas_robots"] += 1
        return None

    html = baixar(sessao, url)
    if html is None:
        contagem["falha_download"] += 1
        return None

    arquivo.write_text(html, encoding="utf-8")
    contagem["baixadas"] += 1
    return html


# ═══════════════════ Listagem ═══════════════════


def coletar_links(sessao: requests.Session, robots: RobotFileParser) -> dict[str, str]:
    """Percorre as páginas de cada tag e devolve {caminho da notícia: tag}."""
    dominio = urlparse(BASE).netloc
    links: dict[str, str] = {}

    for tag in TAGS:
        for pagina in range(MAX_PAGINAS_POR_TAG):
            url = f"{BASE}/tags/{tag}" + (f"?page={pagina}" if pagina else "")

            if not robots.can_fetch(USER_AGENT, url):
                logging.warning("Bloqueado pelo robots.txt: %s", url)
                break

            html = baixar(sessao, url)
            if html is None:
                break

            soup = BeautifulSoup(html, "html.parser")
            novos = 0
            for ancora in soup.find_all("a", href=True):
                destino = urlparse(urljoin(BASE, ancora["href"]))
                if destino.netloc != dominio:
                    continue
                if PADRAO_NOTICIA.match(destino.path) and destino.path not in links:
                    links[destino.path] = tag
                    novos += 1

            logging.info("  tag '%s', página %d: %d links novos", tag, pagina, novos)
            if novos == 0:
                break  # fim da paginação ou só repetidos

    logging.info("Total de notícias distintas encontradas: %d", len(links))
    return links


# ═══════════════════ Extração ═══════════════════


def ler_meta(soup: BeautifulSoup, *nomes: str) -> str | None:
    for nome in nomes:
        tag = soup.find("meta", attrs={"property": nome}) or soup.find(
            "meta", attrs={"name": nome}
        )
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def extrair_corpo(soup: BeautifulSoup) -> str:
    """Escolhe o elemento cujos parágrafos <p> somam mais texto."""
    for ruido in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        ruido.decompose()

    volume_por_pai: dict[int, int] = Counter()
    pais: dict[int, object] = {}
    for paragrafo in soup.find_all("p"):
        pai = paragrafo.parent
        volume_por_pai[id(pai)] += len(paragrafo.get_text(strip=True))
        pais[id(pai)] = pai

    if not volume_por_pai:
        return ""

    melhor = pais[max(volume_por_pai, key=volume_por_pai.get)]
    paragrafos = [
        p.get_text(" ", strip=True)
        for p in melhor.find_all("p", recursive=False)
        if len(p.get_text(strip=True)) >= TAMANHO_MINIMO_PARAGRAFO
    ]
    return "\n".join(paragrafos)


def ufs_mencionadas(texto: str) -> str:
    """Siglas das UFs cujo nome aparece no texto, separadas por vírgula."""
    encontradas = []
    for sigla, (_, nome) in esquema.UFS.items():
        padrao = rf"\b{re.escape(nome)}\b"
        if nome == "Mato Grosso":
            padrao += r"(?! do Sul)"
        if re.search(padrao, texto):
            encontradas.append(sigla)
    return ",".join(encontradas)


def extrair_noticia(html: str, caminho_url: str, tag: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    titulo = ler_meta(soup, "og:title")
    if not titulo and soup.h1:
        titulo = soup.h1.get_text(strip=True)

    linha_fina = ler_meta(soup, "og:description", "description")

    correspondencia = PADRAO_DATA.search(soup.get_text(" ", strip=True))
    data_publicacao = (
        datetime.strptime(
            f"{correspondencia[1]} {correspondencia[2]}", "%d/%m/%Y %H:%M"
        )
        if correspondencia
        else None
    )

    texto = extrair_corpo(soup)
    url = urljoin(BASE, caminho_url)

    return {
        "id": hashlib.md5(url.encode("utf-8")).hexdigest()[:12],
        "fonte": FONTE,
        "url": url,
        "data_publicacao": data_publicacao,
        "titulo": titulo,
        "linha_fina": linha_fina,
        "texto": texto,
        "ufs_mencionadas": ufs_mencionadas(f"{titulo} {linha_fina} {texto}"),
        "nivel_texto": "integral",
        "tag_origem": tag,
        "coletado_em": datetime.now().replace(microsecond=0),
        "resumo": None,  # TP4
        "sentimento": None,  # TP4
    }


# ═══════════════════ Execução ═══════════════════


def registrar_resumo(corpus: pd.DataFrame, contagem: Counter) -> None:
    logging.info("--- Resumo da coleta ---")
    logging.info("Notícias baixadas agora ....: %d", contagem["baixadas"])
    logging.info("Notícias lidas do cache ....: %d", contagem["cache"])
    logging.info("Bloqueadas pelo robots.txt .: %d", contagem["bloqueadas_robots"])
    logging.info("Falha no download ..........: %d", contagem["falha_download"])
    logging.info("Descartadas — sem corpo ....: %d", contagem["sem_corpo"])
    logging.info("Descartadas — irrelevantes .: %d", contagem["irrelevantes"])
    logging.info("Notícias no corpus .........: %d", len(corpus))

    if corpus.empty:
        return

    datas = corpus["data_publicacao"].dropna()
    if not datas.empty:
        logging.info("Período: %s a %s", datas.min().date(), datas.max().date())
    logging.info("Sem data identificada: %d", corpus["data_publicacao"].isna().sum())
    logging.info(
        "Tamanho médio do texto: %.0f caracteres", corpus["texto"].str.len().mean()
    )

    ufs = Counter(
        uf for lista in corpus["ufs_mencionadas"] if lista for uf in lista.split(",")
    )
    if ufs:
        logging.info("UFs mais mencionadas: %s", ufs.most_common(5))


def coletar_noticias() -> None:
    caminho_log = configurar_logging("NOTICIAS", PASTA_LOGS)
    logging.info("=" * 70)
    logging.info("Coleta de notícias — %s", FONTE)

    PASTA_CACHE.mkdir(parents=True, exist_ok=True)
    PASTA_PROCESSED.mkdir(parents=True, exist_ok=True)

    robots = carregar_robots()
    sessao = requests.Session()
    sessao.headers.update({"User-Agent": USER_AGENT})

    links = coletar_links(sessao, robots)
    if not links:
        logging.error("Nenhuma notícia encontrada. Verifique as tags e o robots.txt.")
        sys.exit(1)

    contagem: Counter = Counter()
    registros = []

    for numero, (caminho_url, tag) in enumerate(links.items(), start=1):
        html = obter_html_noticia(sessao, robots, caminho_url, contagem)
        if html is None:
            continue

        noticia = extrair_noticia(html, caminho_url, tag)

        if not noticia["texto"]:
            contagem["sem_corpo"] += 1
            continue

        conteudo = f"{noticia['titulo']} {noticia['linha_fina']} {noticia['texto']}"
        if not PADRAO_RELEVANCIA.search(conteudo):
            contagem["irrelevantes"] += 1
            continue

        registros.append(noticia)
        if numero % 10 == 0:
            logging.info("  %d/%d notícias processadas", numero, len(links))

    corpus = pd.DataFrame(registros)
    if not corpus.empty:
        corpus = corpus.sort_values("data_publicacao", ascending=False)
    corpus.to_csv(SAIDA_CORPUS, index=False, sep=SEPARADOR, encoding="utf-8")

    registrar_resumo(corpus, contagem)
    logging.info("Salvo: %s", SAIDA_CORPUS)
    logging.info("Log da sessão: %s", caminho_log)
    logging.info("=" * 70)


if __name__ == "__main__":
    coletar_noticias()
