"""
PROJETO: SolarGap Brasil
ARQUIVO: noticias/coletor.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026 (fluxo do noticias.py do TP2, generalizado)
ATUALIZAÇÃO:

DESCRIÇÃO:
    Orquestra a coleta de todas as fontes habilitadas e grava o corpus.

FLUXO POR FONTE:
    HTML: listagens -> links (padrão de URL da fonte) -> matéria (cache em
          data/raw/html/<fonte>/) -> extração -> filtro de relevância
    RSS:  feed -> itens (título, link, data, descrição) -> filtro de relevância.
          Nenhuma matéria é baixada: nível "metadados".

MESCLA INCREMENTAL (preparação para o TP4):
    O corpus versionado é o ponto de partida de cada execução:
        - notícias já presentes são PRESERVADAS como estão — inclusive resumo e
          sentimento, que o modelo de linguagem preencherá no TP4. Uma nova
          coleta jamais apaga o trabalho do modelo;
        - só ids novos são baixados e extraídos (economia de requisições);
        - --reprocessar reextrai as já presentes a partir do cache, ainda
          preservando resumo e sentimento;
        - a mesma notícia publicada por duas fontes (mesmo título normalizado)
          é mantida uma vez, preferindo o registro com texto integral.

ISOLAMENTO DE FALHAS:
    Uma fonte fora do ar não derruba as outras: o erro vai para o log e a
    coleta segue. O corpus só é regravado ao final.

SAÍDA:
    data/processed/corpus_noticias.csv (esquema em esquema.COLUNAS_CORPUS)
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
from bs4 import BeautifulSoup

from src.data_acquisition.coletor_base import configurar_logging, obter_project_root
from src.data_acquisition.noticias.base import (
    Navegador,
    converter_data,
    eh_relevante,
    extrair_corpo,
    extrair_data,
    ler_meta,
    limpar_html,
    normalizar_titulo,
)
from src.data_acquisition.noticias.fontes import (
    FONTES,
    FONTES_POR_CHAVE,
    NAO_INCLUIDAS,
    Fonte,
)
from src.preparacao import esquema
from src.servicos.texto import detectar_ufs

PROJECT_ROOT = obter_project_root(__file__, niveis_acima=3)
PASTA_CACHE = PROJECT_ROOT / "data" / "raw" / "html"
PASTA_PROCESSED = PROJECT_ROOT / "data" / "processed"
PASTA_LOGS = PROJECT_ROOT / "logs"
SAIDA_CORPUS = PASTA_PROCESSED / "corpus_noticias.csv"

SEPARADOR = ";"
LIMITE_LINHA_FINA_RSS = 300


# ═══════════════════ Registro ═══════════════════


def montar_registro(
    fonte: Fonte, url: str, titulo, linha_fina, texto, data_publicacao, rotulo
) -> dict:
    return {
        "id": esquema.id_noticia(url),
        "fonte": fonte.nome,
        "url": url,
        "data_publicacao": data_publicacao,
        "titulo": titulo,
        "linha_fina": linha_fina or None,
        "texto": texto or None,
        "ufs_mencionadas": detectar_ufs(f"{titulo} {linha_fina or ''} {texto or ''}"),
        "nivel_texto": fonte.nivel_texto,
        "tag_origem": rotulo,
        "coletado_em": datetime.now().replace(microsecond=0),
        "resumo": None,  # TP4
        "sentimento": None,  # TP4
    }


# ═══════════════════ Fontes HTML ═══════════════════


def caminho_cache(fonte: Fonte, caminho_url: str, pasta: Path | None = None) -> Path:
    """/economia/noticia/2023-08/slug -> data/raw/html/agenciabrasil/2023-08_slug.html"""
    partes = caminho_url.strip("/").split("/")
    pasta = pasta or PASTA_CACHE  # resolvido na chamada: os testes trocam PASTA_CACHE
    return pasta / fonte.chave / f"{partes[-2]}_{partes[-1]}.html"


def coletar_links(
    fonte: Fonte, navegador: Navegador, contagem: Counter
) -> dict[str, str]:
    """Percorre as listagens da fonte e devolve {caminho da notícia: rótulo}."""
    dominio = urlparse(fonte.base).netloc
    links: dict[str, str] = {}

    for listagem in fonte.listagens:
        for pagina in range(listagem.max_paginas):
            url = listagem.montar_url(pagina)
            if not navegador.pode_acessar(url):
                logging.warning("Bloqueado pelo robots.txt: %s", url)
                contagem["listagens_bloqueadas"] += 1
                break
            html = navegador.baixar(url)
            if html is None:
                break

            novos = 0
            for ancora in BeautifulSoup(html, "html.parser").find_all("a", href=True):
                destino = urlparse(urljoin(fonte.base, ancora["href"]))
                caminho = destino.path.rstrip("/")
                if (
                    destino.netloc != dominio
                    or not fonte.padrao_link.match(caminho)
                    or caminho in links
                ):
                    continue
                if listagem.prefiltrar_titulo and not eh_relevante(
                    ancora.get_text(" ", strip=True)
                ):
                    contagem["descartadas_prefiltro"] += 1
                    continue
                links[caminho] = listagem.rotulo
                novos += 1

            logging.info(
                "  %s, página %d: %d links novos", listagem.rotulo, pagina, novos
            )
            if novos == 0:
                break  # fim da paginação ou só repetidos

    logging.info("  %s: %d notícias distintas nas listagens", fonte.nome, len(links))
    return links


def obter_html(
    fonte: Fonte, navegador: Navegador, caminho_url: str, contagem: Counter
) -> str | None:
    arquivo = caminho_cache(fonte, caminho_url)
    if arquivo.exists():
        contagem["cache"] += 1
        return arquivo.read_text(encoding="utf-8")

    url = urljoin(fonte.base, caminho_url)
    if not navegador.pode_acessar(url):
        logging.warning("Bloqueado pelo robots.txt: %s", url)
        contagem["bloqueadas_robots"] += 1
        return None

    html = navegador.baixar(url)
    if html is None:
        contagem["falha_download"] += 1
        return None

    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(html, encoding="utf-8")
    contagem["baixadas"] += 1
    return html


def extrair_noticia(fonte: Fonte, html: str, caminho_url: str, rotulo: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    titulo = ler_meta(soup, "og:title") or (
        soup.h1.get_text(strip=True) if soup.h1 else None
    )
    linha_fina = ler_meta(soup, "og:description", "description")
    data_publicacao = extrair_data(soup, fonte.padrao_data_texto)
    texto = extrair_corpo(soup, fonte.descartar_paragrafos)
    return montar_registro(
        fonte,
        urljoin(fonte.base, caminho_url),
        titulo,
        linha_fina,
        texto,
        data_publicacao,
        rotulo,
    )


def coletar_fonte_html(
    fonte: Fonte, navegador: Navegador, ids_existentes: set[str], reprocessar: bool
) -> tuple[list[dict], Counter]:
    contagem: Counter = Counter()
    registros = []
    links = coletar_links(fonte, navegador, contagem)

    for caminho_url, rotulo in links.items():
        if (
            not reprocessar
            and esquema.id_noticia(urljoin(fonte.base, caminho_url)) in ids_existentes
        ):
            contagem["ja_no_corpus"] += 1
            continue

        html = obter_html(fonte, navegador, caminho_url, contagem)
        if html is None:
            continue

        noticia = extrair_noticia(fonte, html, caminho_url, rotulo)
        if not noticia["texto"]:
            contagem["sem_corpo"] += 1
            continue
        if not eh_relevante(noticia["titulo"], noticia["linha_fina"], noticia["texto"]):
            contagem["irrelevantes"] += 1
            continue
        registros.append(noticia)

    return registros, contagem


# ═══════════════════ Fontes RSS (metadados) ═══════════════════


def extrair_itens_rss(
    fonte: Fonte, xml: str, rotulo: str
) -> tuple[list[dict], Counter]:
    contagem: Counter = Counter()
    registros = []
    for item in BeautifulSoup(xml, "xml").find_all("item"):
        titulo = item.title.get_text(strip=True) if item.title else ""
        link = item.link.get_text(strip=True) if item.link else ""
        if not titulo or not link:
            contagem["itens_incompletos"] += 1
            continue
        descricao = limpar_html(
            item.description.get_text() if item.description else "",
            LIMITE_LINHA_FINA_RSS,
        )
        categorias = " ".join(
            c.get_text(" ", strip=True) for c in item.find_all("category")
        )
        if not eh_relevante(titulo, descricao, categorias):
            contagem["irrelevantes"] += 1
            continue
        data = converter_data(
            item.pubDate.get_text(strip=True) if item.pubDate else None
        )
        registros.append(
            montar_registro(fonte, link, titulo, descricao, None, data, rotulo)
        )
    return registros, contagem


def coletar_fonte_rss(
    fonte: Fonte, navegador: Navegador, ids_existentes: set[str], reprocessar: bool
) -> tuple[list[dict], Counter]:
    contagem: Counter = Counter()
    registros = []
    for feed in fonte.feeds:
        if not navegador.pode_acessar(feed):
            logging.warning("Bloqueado pelo robots.txt: %s", feed)
            contagem["listagens_bloqueadas"] += 1
            continue
        xml = navegador.baixar(feed)
        if xml is None:
            continue
        itens, parcial = extrair_itens_rss(fonte, xml, f"rss:{urlparse(feed).path}")
        contagem.update(parcial)
        for item in itens:
            if not reprocessar and item["id"] in ids_existentes:
                contagem["ja_no_corpus"] += 1
                continue
            registros.append(item)
    return registros, contagem


# ═══════════════════ Corpus ═══════════════════


def carregar_corpus_existente(caminho: Path = SAIDA_CORPUS) -> pd.DataFrame:
    if not caminho.exists():
        return pd.DataFrame(columns=esquema.COLUNAS_CORPUS)
    return pd.read_csv(
        caminho, sep=SEPARADOR, parse_dates=["data_publicacao", "coletado_em"]
    )


def mesclar_corpus(
    existente: pd.DataFrame, novos: list[dict], reprocessar: bool = False
) -> tuple[pd.DataFrame, Counter]:
    """Une o corpus atual às notícias novas (regras no cabeçalho do módulo)."""
    estatisticas: Counter = Counter()
    novos_df = pd.DataFrame(novos, columns=esquema.COLUNAS_CORPUS)
    if novos_df.empty:
        return existente[esquema.COLUNAS_CORPUS].copy(), estatisticas

    ids_antigos = set(existente["id"])
    estatisticas["novas"] = int((~novos_df["id"].isin(ids_antigos)).sum())
    estatisticas["reprocessadas"] = int(novos_df["id"].isin(ids_antigos).sum())

    # Novos à frente quando reprocessar (substituem); atrás quando não (só acrescentam).
    partes = [novos_df, existente] if reprocessar else [existente, novos_df]
    corpus = pd.concat([p for p in partes if not p.empty], ignore_index=True)
    corpus = corpus.drop_duplicates(subset="id", keep="first")

    # O que o modelo já preencheu nunca se perde, nem no reprocessamento.
    if not existente.empty:
        preenchido = existente.set_index("id")
        for coluna in esquema.COLUNAS_MODELO:
            anterior = corpus["id"].map(preenchido[coluna])
            corpus[coluna] = corpus[coluna].where(corpus[coluna].notna(), anterior)

    # Mesma notícia em duas fontes: fica uma, preferindo texto integral.
    corpus["_chave"] = corpus["titulo"].map(normalizar_titulo)
    corpus["_prioridade"] = (corpus["nivel_texto"] != esquema.NIVEL_INTEGRAL).astype(
        int
    )
    antes = len(corpus)
    corpus = corpus.sort_values(["_prioridade"], kind="stable").drop_duplicates(
        "_chave", keep="first"
    )
    estatisticas["duplicadas_entre_fontes"] = antes - len(corpus)

    corpus = corpus.sort_values(
        "data_publicacao", ascending=False, na_position="last", kind="stable"
    )
    return corpus[esquema.COLUNAS_CORPUS].reset_index(drop=True), estatisticas


def registrar_resumo(
    corpus: pd.DataFrame, por_fonte: dict[str, Counter], estatisticas: Counter
) -> None:
    logging.info("--- Resumo por fonte ---")
    for nome, contagem in por_fonte.items():
        detalhes = ", ".join(
            f"{chave}={valor}" for chave, valor in sorted(contagem.items())
        )
        logging.info("  %-15s %s", nome, detalhes or "nenhuma notícia nova")
    logging.info("--- Corpus ---")
    logging.info("Notícias novas ............: %d", estatisticas["novas"])
    logging.info("Reprocessadas .............: %d", estatisticas["reprocessadas"])
    logging.info(
        "Duplicadas entre fontes ...: %d", estatisticas["duplicadas_entre_fontes"]
    )
    logging.info("Total no corpus ...........: %d", len(corpus))
    for fonte, quantidade in corpus["fonte"].value_counts().items():
        logging.info("  %-15s %d", fonte, quantidade)
    datas = pd.to_datetime(corpus["data_publicacao"], errors="coerce").dropna()
    if not datas.empty:
        logging.info("Período: %s a %s", datas.min().date(), datas.max().date())


def coletar_noticias(
    chaves: list[str] | None = None, reprocessar: bool = False
) -> pd.DataFrame:
    caminho_log = configurar_logging("NOTICIAS", PASTA_LOGS)
    logging.info("=" * 70)
    logging.info("Coleta de notícias — TP3 (multifonte)")

    if chaves:
        desconhecidas = sorted(set(chaves) - set(FONTES_POR_CHAVE))
        if desconhecidas:
            raise SystemExit(f"Fontes desconhecidas: {desconhecidas}. Use --listar.")
        fontes = [FONTES_POR_CHAVE[c] for c in chaves]
    else:
        fontes = [f for f in FONTES if f.habilitada]

    for fonte in FONTES:
        if fonte in fontes and not fonte.habilitada:
            logging.warning("%s está DESABILITADA: %s", fonte.nome, fonte.motivo)
    fontes = [f for f in fontes if f.habilitada]
    for nome, motivo in NAO_INCLUIDAS.items():
        logging.info("Não incluída — %s: %s", nome, motivo)

    existente = carregar_corpus_existente()
    ids_existentes = set(existente["id"])
    navegador = Navegador()
    novos: list[dict] = []
    por_fonte: dict[str, Counter] = {}

    for fonte in fontes:
        logging.info(
            "Fonte: %s (%s, nível %s)", fonte.nome, fonte.tipo, fonte.nivel_texto
        )
        coletar = coletar_fonte_rss if fonte.tipo == "rss" else coletar_fonte_html
        try:
            registros, contagem = coletar(fonte, navegador, ids_existentes, reprocessar)
        except Exception as erro:  # noqa: BLE001 — uma fonte não derruba as demais
            logging.exception("Falha inesperada na fonte %s: %s", fonte.nome, erro)
            por_fonte[fonte.nome] = Counter({"erro": 1})
            continue
        contagem["aproveitadas"] = len(registros)
        por_fonte[fonte.nome] = contagem
        novos.extend(registros)

    corpus, estatisticas = mesclar_corpus(existente, novos, reprocessar)
    PASTA_PROCESSED.mkdir(parents=True, exist_ok=True)
    corpus.to_csv(SAIDA_CORPUS, index=False, sep=SEPARADOR, encoding="utf-8")

    registrar_resumo(corpus, por_fonte, estatisticas)
    logging.info("Salvo: %s", SAIDA_CORPUS)
    logging.info("Log da sessão: %s", caminho_log)
    logging.info("=" * 70)
    return corpus
