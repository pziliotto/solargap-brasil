"""
PROJETO: SolarGap Brasil
ARQUIVO: noticias/base.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026 (funções extraídas do noticias.py do TP2)
ATUALIZAÇÃO:

DESCRIÇÃO:
    Infraestrutura comum a todas as fontes de notícias.

NAVEGAÇÃO EDUCADA (classe Navegador):
    - robots.txt lido UMA vez por domínio e consultado antes de cada URL;
    - robots.txt baixado pela própria sessão, com o User-Agent do projeto. O
      leitor padrão do Python (urllib) se identifica como "Python-urllib", que
      alguns sites bloqueiam — o resultado seria um falso "proibido";
    - robots.txt ilegível (falha de rede) = NÃO coletar o domínio. Na dúvida,
      o projeto não acessa;
    - Crawl-delay do robots.txt respeitado quando maior que a pausa padrão;
    - retry com espera exponencial (calcular_espera_backoff, coletor_base).

EXTRAÇÃO INDEPENDENTE DE LAYOUT:
    Classes CSS mudam a cada redesenho do site; padrões abertos, não:
        - data: texto da página (padrão da fonte) -> meta article:published_time
                -> meta Dublin Core (DC.date.created) -> JSON-LD datePublished;
        - título e linha fina: meta tags Open Graph (og:title, og:description);
        - corpo: o elemento cujos parágrafos <p> somam mais texto.
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from src.data_acquisition.coletor_base import calcular_espera_backoff

USER_AGENT = "SolarGapBrasil/1.0 (projeto academico de ciencia de dados; INFNET)"
PAUSA_SEGUNDOS = 1.5
TENTATIVAS = 3
TIMEOUT = 30
FUSO = ZoneInfo("America/Sao_Paulo")

PADRAO_RELEVANCIA = re.compile(
    r"solar|fotovolt|gera[çc][ãa]o\s+(?:pr[óo]pria\s+|de\s+energia\s+)?distribu[íi]da|"
    r"\bMMGD\b|\bGD\b|micro\s*e\s*minigera|minigera[çc][ãa]o|microgera[çc][ãa]o",
    re.IGNORECASE,
)
TAMANHO_MINIMO_PARAGRAFO = 40
FORMATOS_DATA = ("%d/%m/%Y %H:%M", "%d/%m/%Y %Hh%M", "%d/%m/%Y")


# ═══════════════════ Navegação ═══════════════════


class Navegador:
    """Sessão HTTP que respeita robots.txt, pausa e retry."""

    def __init__(
        self,
        user_agent: str = USER_AGENT,
        pausa: float = PAUSA_SEGUNDOS,
        sessao: requests.Session | None = None,
    ):
        self.user_agent = user_agent
        self.pausa = pausa
        self.sessao = sessao or requests.Session()
        self.sessao.headers.update({"User-Agent": user_agent})
        self._robots: dict[str, RobotFileParser | None] = {}

    def _robots_do_dominio(self, url: str) -> RobotFileParser | None:
        partes = urlparse(url)
        raiz = f"{partes.scheme}://{partes.netloc}"
        if raiz in self._robots:
            return self._robots[raiz]

        leitor: RobotFileParser | None = RobotFileParser(f"{raiz}/robots.txt")
        try:
            resposta = self.sessao.get(f"{raiz}/robots.txt", timeout=TIMEOUT)
            if resposta.status_code in (401, 403):
                leitor.disallow_all = True  # mesma convenção do urllib.robotparser
            elif resposta.status_code >= 400:
                leitor.allow_all = True  # sem robots.txt = sem restrições declaradas
            else:
                leitor.parse(resposta.text.splitlines())
            logging.info(
                "robots.txt de %s carregado (HTTP %d).",
                partes.netloc,
                resposta.status_code,
            )
        except requests.exceptions.RequestException as erro:
            logging.error(
                "robots.txt ilegível em %s — domínio não será coletado: %s", raiz, erro
            )
            leitor = None

        self._robots[raiz] = leitor
        return leitor

    def diagnosticar(self, url: str) -> str:
        """'permitido', 'proibido' ou 'ilegivel' (robots.txt não pôde ser lido)."""
        leitor = self._robots_do_dominio(url)
        if leitor is None:
            return "ilegivel"
        return "permitido" if leitor.can_fetch(self.user_agent, url) else "proibido"

    def pode_acessar(self, url: str) -> bool:
        leitor = self._robots_do_dominio(url)
        return leitor is not None and leitor.can_fetch(self.user_agent, url)

    def _pausa_para(self, url: str) -> float:
        leitor = self._robots_do_dominio(url)
        atraso = leitor.crawl_delay(self.user_agent) if leitor else None
        return max(self.pausa, float(atraso or 0))

    def baixar(self, url: str) -> str | None:
        """GET com retry e backoff. Devolve None para 404 ou falha persistente."""
        for tentativa in range(1, TENTATIVAS + 1):
            try:
                resposta = self.sessao.get(url, timeout=TIMEOUT)
                time.sleep(self._pausa_para(url))

                if resposta.status_code == 404:
                    logging.warning("Página inexistente (404): %s", url)
                    return None
                resposta.raise_for_status()
                resposta.encoding = resposta.apparent_encoding or "utf-8"
                return resposta.text

            except requests.exceptions.RequestException as erro:
                logging.warning(
                    "Falha na tentativa %d/%d (%s): %s",
                    tentativa,
                    TENTATIVAS,
                    url,
                    erro,
                )
                if tentativa < TENTATIVAS:
                    time.sleep(calcular_espera_backoff(tentativa, 2))

        logging.error("Desistindo após %d tentativas: %s", TENTATIVAS, url)
        return None


# ═══════════════════ Extração ═══════════════════


def ler_meta(soup: BeautifulSoup, *nomes: str) -> str | None:
    for nome in nomes:
        tag = soup.find("meta", attrs={"property": nome}) or soup.find(
            "meta", attrs={"name": nome}
        )
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def converter_data(valor: str | None) -> datetime | None:
    """ISO 8601, RFC 822 (RSS) ou DD/MM/AAAA [HH:MM] -> datetime local, sem fuso."""
    if not valor:
        return None
    valor = valor.strip()
    data: datetime | None = None

    try:
        data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        for formato in FORMATOS_DATA:
            try:
                data = datetime.strptime(valor, formato)
                break
            except ValueError:
                continue
    if data is None:
        try:
            data = parsedate_to_datetime(valor)  # "Tue, 21 Oct 2026 10:00:00 -0300"
        except (TypeError, ValueError):
            return None

    if data.tzinfo is not None:
        data = data.astimezone(FUSO).replace(tzinfo=None)
    return data


def _data_json_ld(soup: BeautifulSoup) -> str | None:
    """Procura datePublished em blocos JSON-LD, inclusive dentro de @graph."""

    def procurar(no):
        if isinstance(no, dict):
            if "datePublished" in no:
                return no["datePublished"]
            for valor in no.values():
                achado = procurar(valor)
                if achado:
                    return achado
        elif isinstance(no, list):
            for item in no:
                achado = procurar(item)
                if achado:
                    return achado
        return None

    for bloco in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            achado = procurar(json.loads(bloco.string or ""))
        except json.JSONDecodeError:
            continue
        if achado:
            return achado
    return None


def extrair_data(
    soup: BeautifulSoup, padrao_texto: re.Pattern | None = None
) -> datetime | None:
    if padrao_texto is not None:
        correspondencia = padrao_texto.search(soup.get_text(" ", strip=True))
        if correspondencia:
            data = converter_data(" ".join(correspondencia.groups()))
            if data:
                return data

    meta = ler_meta(
        soup, "article:published_time", "DC.date.created", "DC.date.issued", "date"
    )
    return converter_data(meta) or converter_data(_data_json_ld(soup))


def extrair_corpo(soup: BeautifulSoup, descartar: tuple[re.Pattern, ...] = ()) -> str:
    """Escolhe o elemento cujos parágrafos <p> somam mais texto.

    descartar: padrões de parágrafos fixos da fonte (créditos, avisos de
    reprodução, links), removidos para não poluir o corpus nem o LLM.
    """
    for ruido in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        ruido.decompose()

    volume_por_pai: dict[int, int] = {}
    pais: dict[int, object] = {}
    for paragrafo in soup.find_all("p"):
        pai = paragrafo.parent
        volume_por_pai[id(pai)] = volume_por_pai.get(id(pai), 0) + len(
            paragrafo.get_text(strip=True)
        )
        pais[id(pai)] = pai

    if not volume_por_pai:
        return ""

    melhor = pais[max(volume_por_pai, key=volume_por_pai.get)]
    paragrafos = []
    for paragrafo in melhor.find_all("p", recursive=False):
        texto = paragrafo.get_text(" ", strip=True)
        if len(texto) < TAMANHO_MINIMO_PARAGRAFO:
            continue
        if any(padrao.search(texto) for padrao in descartar):
            continue
        paragrafos.append(texto)
    return "\n".join(paragrafos)


def eh_relevante(*textos: str | None) -> bool:
    return bool(PADRAO_RELEVANCIA.search(" ".join(t for t in textos if t)))


def limpar_html(fragmento: str | None, limite: int | None = None) -> str:
    """Texto puro de um trecho HTML (ex.: descrição de feed RSS), cortado sem partir palavras."""
    if not fragmento:
        return ""
    texto = BeautifulSoup(fragmento, "html.parser").get_text(" ", strip=True)
    texto = re.sub(r"\s+", " ", texto)
    if limite and len(texto) > limite:
        corte = texto.rfind(" ", 0, limite)
        texto = texto[: corte if corte > 0 else limite].rstrip() + "..."
    return texto


def normalizar_titulo(titulo: str | None) -> str:
    """Chave para detectar a mesma notícia publicada por duas fontes."""
    sem_acento = (
        unicodedata.normalize("NFKD", str(titulo or ""))
        .encode("ascii", "ignore")
        .decode()
    )
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()
