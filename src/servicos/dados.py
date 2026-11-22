"""
PROJETO: SolarGap Brasil
ARQUIVO: dados.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Leitura dos arquivos consumidos pela aplicação e pela API. É o único ponto
    do projeto que conhece caminhos de arquivo da camada Gold.

ARQUIVOS:
    data/processed/gold_mmgd_agregado.csv   fato: UF x ano x classe x imputado
    data/processed/gold_uf.csv              dimensão UF + indicadores do período
    data/processed/gold_icms_uf.csv         dimensão de política (Convênio ICMS 16/15)
    data/processed/corpus_noticias.csv      corpus coletado pelos scrapers
    data/external/noticias_enviadas.csv     notícias recebidas pela API (POST)

DECISÕES:
    - Arquivos obrigatórios ausentes levantam DadosIndisponiveis, uma exceção
      própria: a API a traduz em HTTP 503 e o painel, em mensagem amigável.
    - Arquivos opcionais (ICMS, notícias enviadas) ausentes devolvem None ou
      DataFrame vazio com o esquema correto — a aplicação segue funcionando.
    - Sem cache aqui: cada consumidor decide o seu (st.cache_data no painel,
      carga única no startup da API).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data_acquisition.coletor_base import obter_project_root
from src.preparacao import esquema

PROJECT_ROOT = obter_project_root(__file__)
PASTA_PROCESSED = PROJECT_ROOT / "data" / "processed"
PASTA_EXTERNAL = PROJECT_ROOT / "data" / "external"

ARQUIVO_AGREGADO = "gold_mmgd_agregado.csv"
ARQUIVO_UF = "gold_uf.csv"
ARQUIVO_ICMS = "gold_icms_uf.csv"
ARQUIVO_CORPUS = "corpus_noticias.csv"
ARQUIVO_NOTICIAS_ENVIADAS = "noticias_enviadas.csv"

SEPARADOR = ";"
COLUNAS_DATA_CORPUS = ["data_publicacao", "coletado_em"]


class DadosIndisponiveis(RuntimeError):
    """Arquivo obrigatório da camada Gold não encontrado ou ilegível."""


def _ler_obrigatorio(caminho: Path, **kwargs) -> pd.DataFrame:
    if not caminho.exists():
        raise DadosIndisponiveis(
            f"Arquivo obrigatório não encontrado: {caminho.name}. "
            "Rode o pipeline (construir_silver/construir_gold) ou restaure o arquivo do repositório."
        )
    try:
        return pd.read_csv(caminho, sep=SEPARADOR, **kwargs)
    except Exception as erro:  # noqa: BLE001 — qualquer falha de leitura vira 503
        raise DadosIndisponiveis(f"Falha ao ler {caminho.name}: {erro}") from erro


# ═══════════════════ Indicadores (ANEEL + IBGE) ═══════════════════


def carregar_agregado(pasta: Path = PASTA_PROCESSED) -> pd.DataFrame:
    return _ler_obrigatorio(pasta / ARQUIVO_AGREGADO)


def carregar_uf(pasta: Path = PASTA_PROCESSED) -> pd.DataFrame:
    return _ler_obrigatorio(pasta / ARQUIVO_UF)


def carregar_icms(pasta: Path = PASTA_PROCESSED) -> pd.DataFrame | None:
    """Adesão ao Convênio ICMS 16/15 por UF. Opcional: None se ainda não coletado."""
    caminho = pasta / ARQUIVO_ICMS
    if not caminho.exists():
        return None
    return pd.read_csv(
        caminho, sep=SEPARADOR, parse_dates=["data_adesao", "inicio_efeitos"]
    )


# ═══════════════════ Notícias ═══════════════════


def _preparar_corpus(corpus: pd.DataFrame) -> pd.DataFrame:
    """Garante esquema, tipos e campos de texto sem NaN."""
    for coluna in esquema.COLUNAS_CORPUS:
        if coluna not in corpus.columns:
            corpus[coluna] = pd.NA
    corpus = corpus[esquema.COLUNAS_CORPUS].copy()

    for coluna in COLUNAS_DATA_CORPUS:
        corpus[coluna] = pd.to_datetime(corpus[coluna], errors="coerce")

    for coluna in ["ufs_mencionadas", "linha_fina", "texto", "titulo", "fonte"]:
        corpus[coluna] = corpus[coluna].fillna("").astype(str)

    return corpus


def corpus_vazio() -> pd.DataFrame:
    return _preparar_corpus(pd.DataFrame(columns=esquema.COLUNAS_CORPUS))


def carregar_corpus(pasta: Path = PASTA_PROCESSED) -> pd.DataFrame:
    return _preparar_corpus(_ler_obrigatorio(pasta / ARQUIVO_CORPUS))


def caminho_noticias_enviadas(pasta: Path = PASTA_EXTERNAL) -> Path:
    return pasta / ARQUIVO_NOTICIAS_ENVIADAS


def carregar_noticias_enviadas(pasta: Path = PASTA_EXTERNAL) -> pd.DataFrame:
    caminho = caminho_noticias_enviadas(pasta)
    if not caminho.exists():
        return corpus_vazio()
    return _preparar_corpus(pd.read_csv(caminho, sep=SEPARADOR))


def carregar_corpus_ia(pasta: Path = PASTA_PROCESSED) -> pd.DataFrame | None:
    """Resumo e relevância gerados pelos modelos locais (TP4). Opcional."""
    caminho = pasta / esquema.ARQUIVO_CORPUS_IA
    if not caminho.exists():
        return None
    ia = pd.read_csv(caminho, sep=SEPARADOR, dtype={"id": str})
    for coluna in esquema.COLUNAS_CORPUS_IA:
        if coluna not in ia.columns:
            ia[coluna] = pd.NA
    return ia[esquema.COLUNAS_CORPUS_IA].drop_duplicates(subset="id", keep="last")


def anexar_ia(corpus: pd.DataFrame, ia: pd.DataFrame | None) -> pd.DataFrame:
    """Junta o enriquecimento por IA ao corpus pelo id.

    O resumo do arquivo de IA preenche a coluna resumo do corpus (prevalece um
    resumo já existente no corpus, se houver). Notícias ainda não processadas
    ficam com relevante/relevancia_prob nulos — "não avaliada", não "irrelevante".
    """
    extras = [
        "relevante",
        "relevancia_prob",
        "relevancia_por_termo",
        "resumo_truncado",
    ]
    if ia is None or ia.empty:
        return _sem_resumo_derivado(
            corpus.assign(**{coluna: pd.NA for coluna in extras})
        )
    ia = ia.reindex(
        columns=["id", "resumo", *extras]
    )  # arquivos antigos sem colunas novas
    unido = corpus.merge(
        ia.rename(columns={"resumo": "resumo_ia"}),
        on="id",
        how="left",
    )
    # A coluna resumo do corpus costuma estar toda vazia (lida como float):
    # converte para objeto antes de receber texto (pandas 3 não aceita upcast).
    resumo = unido["resumo"].astype("object")
    vazio = resumo.isna() | (resumo.astype(str).str.strip() == "")
    unido["resumo"] = resumo.where(~vazio, unido["resumo_ia"].astype("object"))
    for coluna in ("relevante", "relevancia_por_termo"):
        unido[coluna] = unido[coluna].map(
            lambda v: (
                v if pd.isna(v) else str(v).strip().lower() in {"true", "1", "sim"}
            )
        )
    return _sem_resumo_derivado(unido.drop(columns="resumo_ia"))


def _sem_resumo_derivado(corpus: pd.DataFrame) -> pd.DataFrame:
    """Apaga o resumo das fontes cuja licença proíbe obra derivada (CC BY-ND).

    É o único ponto por onde painel e API recebem o resumo: a regra vale para
    os dois e para qualquer resumo antigo que ainda esteja em corpus_ia.csv.
    """
    if "fonte" not in corpus.columns or corpus.empty:
        return corpus
    proibido = corpus["fonte"].isin(esquema.FONTES_SEM_DERIVACAO)
    corpus = corpus.copy()
    for coluna in ("resumo", "resumo_truncado"):
        if coluna in corpus.columns:
            corpus[coluna] = corpus[coluna].astype("object").where(~proibido, None)
    return corpus


def carregar_corpus_completo(
    pasta_processed: Path = PASTA_PROCESSED, pasta_external: Path = PASTA_EXTERNAL
) -> pd.DataFrame:
    """Corpus coletado + notícias enviadas pela API, sem ids repetidos, com o
    enriquecimento por IA (resumo e relevância) quando disponível.

    Em caso de id repetido, prevalece o registro coletado (fonte primária).
    """
    coletado = carregar_corpus(pasta_processed)
    enviadas = carregar_noticias_enviadas(pasta_external)
    ia = carregar_corpus_ia(pasta_processed)
    if enviadas.empty:
        return anexar_ia(coletado, ia)

    completo = pd.concat([coletado, enviadas], ignore_index=True)
    completo = completo.drop_duplicates(subset="id", keep="first")
    completo = completo.sort_values(
        "data_publicacao", ascending=False, na_position="last"
    ).reset_index(drop=True)
    return anexar_ia(completo, ia)
