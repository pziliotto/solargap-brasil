"""
PROJETO: SolarGap Brasil
ARQUIVO: noticias.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Regras de negócio sobre o corpus de notícias, usadas pela API e pelo painel:
        - filtrar_noticias: recortes por fonte, UF, termo, período e nível de texto;
        - registrar_noticia: grava uma notícia recebida pela API (POST /noticias).

ONDE FICAM AS NOTÍCIAS ENVIADAS:
    data/external/noticias_enviadas.csv — arquivo separado do corpus coletado.
    Se a API escrevesse direto em data/processed/corpus_noticias.csv, a próxima
    execução do scraper sobrescreveria (ou misturaria) as contribuições. Separar
    as origens mantém a rastreabilidade: tag_origem = "envio_api".

    O arquivo NÃO é versionado (.gitignore): é estado de execução da API, não
    dado do projeto. Para o painel e a API, o corpus é sempre a união das duas
    origens (dados.carregar_corpus_completo).

CONCORRÊNCIA:
    Um Lock serializa as gravações dentro do processo da API. Suficiente para o
    servidor de desenvolvimento (um processo). Em produção com vários workers,
    a gravação iria para um banco de dados.
"""

from __future__ import annotations

import threading
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from src.preparacao import esquema
from src.servicos import dados
from src.servicos.texto import detectar_ufs

TAG_ENVIO_API = "envio_api"
_TRAVA_GRAVACAO = threading.Lock()


class NoticiaDuplicada(ValueError):
    """Já existe notícia com a mesma URL (mesmo id) no corpus."""


def lista_ufs(valor: str) -> list[str]:
    """'SP,RJ' -> ['SP', 'RJ']; vazio -> []."""
    return [uf for uf in str(valor or "").split(",") if uf]


def filtrar_noticias(
    corpus: pd.DataFrame,
    fonte: str | None = None,
    uf: str | None = None,
    termo: str | None = None,
    desde: date | None = None,
    ate: date | None = None,
    nivel_texto: str | None = None,
) -> pd.DataFrame:
    """Aplica os filtros informados (os ausentes são ignorados)."""
    filtro = pd.Series(True, index=corpus.index)

    if fonte:
        filtro &= corpus["fonte"].str.casefold() == fonte.casefold()
    if uf:
        filtro &= corpus["ufs_mencionadas"].map(lambda v: uf.upper() in lista_ufs(v))
    if termo:
        conteudo = corpus["titulo"] + " " + corpus["linha_fina"] + " " + corpus["texto"]
        filtro &= conteudo.str.contains(termo, case=False, regex=False)
    if desde:
        filtro &= corpus["data_publicacao"] >= pd.Timestamp(desde)
    if ate:
        # inclusivo: até o fim do dia informado
        filtro &= corpus["data_publicacao"] < pd.Timestamp(ate) + pd.Timedelta(days=1)
    if nivel_texto:
        filtro &= corpus["nivel_texto"] == nivel_texto

    return corpus[filtro]


def registrar_noticia(
    fonte: str,
    url: str,
    titulo: str,
    data_publicacao: date,
    linha_fina: str | None = None,
    texto: str | None = None,
    corpus_atual: pd.DataFrame | None = None,
    pasta_external: Path = dados.PASTA_EXTERNAL,
) -> dict:
    """Valida duplicidade, monta o registro no esquema do corpus e grava.

    A validação de formato (URL, tamanhos, data no futuro) é feita antes, pelo
    modelo Pydantic da API. Aqui ficam as regras que dependem do corpus.
    """
    identificador = esquema.id_noticia(url)
    if corpus_atual is None:
        corpus_atual = dados.carregar_corpus_completo(pasta_external=pasta_external)
    if identificador in set(corpus_atual["id"]):
        raise NoticiaDuplicada(f"Já existe notícia com esta URL (id {identificador}).")

    texto = (texto or "").strip() or None
    linha_fina = (linha_fina or "").strip() or None
    registro = {
        "id": identificador,
        "fonte": fonte.strip(),
        "url": url.strip(),
        "data_publicacao": datetime.combine(data_publicacao, datetime.min.time()),
        "titulo": titulo.strip(),
        "linha_fina": linha_fina,
        "texto": texto,
        "ufs_mencionadas": detectar_ufs(f"{titulo} {linha_fina or ''} {texto or ''}"),
        "nivel_texto": esquema.NIVEL_INTEGRAL if texto else esquema.NIVEL_METADADOS,
        "tag_origem": TAG_ENVIO_API,
        "coletado_em": datetime.now().replace(microsecond=0),
        "resumo": None,  # TP4
        "sentimento": None,  # TP4
    }

    caminho = dados.caminho_noticias_enviadas(pasta_external)
    with _TRAVA_GRAVACAO:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        novo_arquivo = not caminho.exists()
        pd.DataFrame([registro], columns=esquema.COLUNAS_CORPUS).to_csv(
            caminho,
            mode="a",
            header=novo_arquivo,
            index=False,
            sep=dados.SEPARADOR,
            encoding="utf-8",
        )
    return registro
