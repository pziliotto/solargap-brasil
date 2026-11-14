"""
PROJETO: SolarGap Brasil
ARQUIVO: rotulagem.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 13/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Gera a planilha docs/benchmark/rotulos_benchmark.csv com 30 notícias para
    rotulagem MANUAL de relevância e tom. Esses rótulos são o gabarito contra o
    qual o benchmark mede os classificadores zero-shot.

AMOSTRA (estratificada, semente fixa):
    - todas as notícias da Agência Gov (fonte com menos itens);
    - o restante da Agência Brasil, dividido igualmente entre três períodos
      (até 2017, 2018-2021, 2022 em diante), para não concentrar em uma época.

FORMATO:
    CSV com ";" e UTF-8 com BOM: abre direto no Excel em português, com acentos.
    Critérios de preenchimento: docs/benchmark/README.md.

OBS. DE USO:
    python -m src.ia.rotulagem               # não sobrescreve rótulos existentes
    python -m src.ia.rotulagem --sobrescrever
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from src.data_acquisition.coletor_base import obter_project_root
from src.servicos import dados

PROJECT_ROOT = obter_project_root(__file__)
PASTA_BENCHMARK = PROJECT_ROOT / "docs" / "benchmark"
ARQUIVO_ROTULOS = PASTA_BENCHMARK / "rotulos_benchmark.csv"

TAMANHO_AMOSTRA = 30
SEMENTE = 42
PERIODOS = [(0, 2017), (2018, 2021), (2022, 9999)]
COLUNAS_ROTULO = ["relevante", "tom", "observacao"]

logger = logging.getLogger(__name__)


def selecionar(corpus: pd.DataFrame, tamanho: int = TAMANHO_AMOSTRA) -> pd.DataFrame:
    corpus = corpus.assign(ano=pd.to_datetime(corpus["data_publicacao"]).dt.year)
    menores = corpus[corpus["fonte"] != "Agência Brasil"]
    restante = corpus[corpus["fonte"] == "Agência Brasil"]
    vagas = tamanho - len(menores)
    por_periodo = [vagas // len(PERIODOS)] * len(PERIODOS)
    por_periodo[-1] += vagas - sum(por_periodo)

    partes = [menores]
    for (inicio, fim), quantidade in zip(PERIODOS, por_periodo):
        grupo = restante[restante["ano"].between(inicio, fim)]
        partes.append(grupo.sample(min(quantidade, len(grupo)), random_state=SEMENTE))

    amostra = pd.concat(partes).sort_values("data_publicacao")
    return amostra[["id", "fonte", "data_publicacao", "titulo", "linha_fina", "url"]]


def gerar(destino: Path = ARQUIVO_ROTULOS, sobrescrever: bool = False) -> Path:
    if destino.exists() and not sobrescrever:
        logger.warning("%s já existe; nada foi alterado (use --sobrescrever).", destino)
        return destino
    amostra = selecionar(dados.carregar_corpus())
    for coluna in COLUNAS_ROTULO:
        amostra[coluna] = ""
    destino.parent.mkdir(parents=True, exist_ok=True)
    amostra.to_csv(destino, sep=";", index=False, encoding="utf-8-sig")
    logger.info("Planilha com %d notícias gravada em %s", len(amostra), destino)
    return destino


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(
        description="Gera a planilha de rótulos do benchmark."
    )
    parser.add_argument("--sobrescrever", action="store_true")
    gerar(sobrescrever=parser.parse_args().sobrescrever)
