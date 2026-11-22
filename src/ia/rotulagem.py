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

BENCHMARK V2 (Tarefa 5a, 20/11/2026) — gerar_v2():
    docs/benchmark/rotulos_benchmark_v2_pendentes.csv, com até 120 notícias
    reais ainda não rotuladas (todo o corpus fora do gabarito v1, sem filtro de
    data de coleta), para a autora rotular com o mesmo guia. IDS_FORA_V2 lista
    as notícias do v1 descobertas por caminho proibido pelo robots.txt que não
    voltaram pelo sitemap; elas ficam fora do v2. Cada notícia recebe a palavra-chave
    mais específica que ela menciona (PALAVRAS_CHAVE, em ordem). Entram de
    propósito notícias de GD (Lei 14.300, fio B, micro/minigeração...) que não
    citam "solar" nem "fotovoltaica": é o caso em que a hipótese de relevância
    atual ("Esta notícia trata de energia solar.") falha. O restante é
    estratificado por fonte x palavra-chave, com alocação proporcional e ao
    menos uma notícia por estrato.

OBS. DE USO:
    python -m src.ia.rotulagem               # não sobrescreve rótulos existentes
    python -m src.ia.rotulagem --sobrescrever
    python -m src.ia.rotulagem --v2          # planilha de pendentes do benchmark v2
"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

import pandas as pd

from src.data_acquisition.coletor_base import obter_project_root
from src.servicos import dados

PROJECT_ROOT = obter_project_root(__file__)
PASTA_BENCHMARK = PROJECT_ROOT / "docs" / "benchmark"
ARQUIVO_ROTULOS = PASTA_BENCHMARK / "rotulos_benchmark.csv"
ARQUIVO_PENDENTES_V2 = PASTA_BENCHMARK / "rotulos_benchmark_v2_pendentes.csv"

TAMANHO_AMOSTRA = 30
SEMENTE = 42
PERIODOS = [(0, 2017), (2018, 2021), (2022, 9999)]
COLUNAS_ROTULO = ["relevante", "tom", "observacao"]

# ── Benchmark v2 ──
TAMANHO_V2 = 120
MAXIMO_GD_SEM_SOLAR = 20
# Notícias do v1 descobertas pela busca da Agência Gov (proibida pelo robots.txt)
# que não voltaram pelo sitemap: sem texto no corpus, ficam fora do v2.
IDS_FORA_V2 = frozenset({"358fa5895453", "a2370b5d680b"})

# Da mais específica para a mais genérica: a notícia fica com a primeira que casar.
PALAVRAS_CHAVE = {
    "Lei 14.300": r"\blei\s+(?:federal\s+)?(?:n[º°o]?\.?\s*)?14\.?300\b",
    "fio B": r"\bfio\s+B\b",
    "compensação de créditos": r"\bcompensa[çc][ãa]o\s+de\s+cr[ée]ditos\b(?!\s+de\s+carbono)",
    "net metering": r"\bnet[\s-]?metering\b",
    "minigeração": r"\bminigera(?:[çc][ãa]o|[çc][õo]es|dor(?:a|es|as)?)\b",
    "microgeração": r"\bmicrogera(?:[çc][ãa]o|[çc][õo]es|dor(?:a|es|as)?)\b",
    "geração distribuída": (
        r"\bgera[çc][ãa]o\s+(?:pr[óo]pria\s+|de\s+energia\s+)?distribu[íi]da\b"
        r"|\bMMGD\b|\bGD\b"
    ),
    "fotovoltaica": r"fotovolt",
    "energia solar": r"solar",
}
PALAVRAS_GD = (
    "Lei 14.300",
    "fio B",
    "compensação de créditos",
    "net metering",
    "minigeração",
    "microgeração",
    "geração distribuída",
)
PADRAO_SOLAR = re.compile(r"solar|fotovolt", re.IGNORECASE)
COLUNAS_V2 = [
    "id",
    "titulo",
    "texto",
    "url",
    "fonte",
    "data_publicacao",
    "palavra_chave",
    "gd_sem_solar",
    "relevante",
    "tom",
    "observacao",
]

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


def _texto_completo(linha: pd.Series) -> str:
    return " ".join(
        str(linha[c]) for c in ("titulo", "linha_fina", "texto") if pd.notna(linha[c])
    )


def palavra_chave(texto: str) -> str:
    """Palavra-chave mais específica mencionada (ver PALAVRAS_CHAVE); 'outra' se nenhuma."""
    for nome, padrao in PALAVRAS_CHAVE.items():
        if re.search(padrao, texto, re.IGNORECASE):
            return nome
    return "outra"


def gd_sem_solar(texto: str) -> bool:
    """Menciona termo de GD, mas não "solar" nem "fotovoltaica"."""
    return palavra_chave(texto) in PALAVRAS_GD and not PADRAO_SOLAR.search(texto)


def alocar(tamanhos: pd.Series, total: int) -> pd.Series:
    """Alocação proporcional com ao menos 1 por estrato (maiores restos), limitada ao tamanho."""
    tamanhos = tamanhos[tamanhos > 0]
    if tamanhos.sum() <= total:
        return tamanhos.copy()
    cota = pd.Series(1, index=tamanhos.index).clip(upper=tamanhos)
    while cota.sum() < total:
        ideal = total * tamanhos / tamanhos.sum()
        folga = (ideal - cota).where(cota < tamanhos, -float("inf"))
        cota[folga.idxmax()] += 1
    return cota


def selecionar_v2(
    corpus: pd.DataFrame,
    ids_excluir: set[str],
    tamanho: int = TAMANHO_V2,
    maximo_gd_sem_solar: int = MAXIMO_GD_SEM_SOLAR,
) -> pd.DataFrame:
    """Notícias reais ainda não rotuladas: todo o corpus menos ids_excluir e IDS_FORA_V2."""
    fora = set(ids_excluir) | IDS_FORA_V2
    candidatas = corpus[~corpus["id"].isin(fora)].copy()
    textos = candidatas.apply(_texto_completo, axis=1)
    candidatas["palavra_chave"] = textos.map(palavra_chave)
    candidatas["gd_sem_solar"] = textos.map(gd_sem_solar)
    candidatas = candidatas.sort_values("id")  # ordem estável antes do sorteio

    gd = candidatas[candidatas["gd_sem_solar"]]
    gd = gd.sample(min(maximo_gd_sem_solar, len(gd)), random_state=SEMENTE)
    resto = candidatas.drop(gd.index)
    vagas = max(tamanho - len(gd), 0)

    cotas = alocar(resto.groupby(["fonte", "palavra_chave"]).size(), vagas)
    partes = [gd]
    for (fonte, chave), quantidade in cotas.items():
        grupo = resto[(resto["fonte"] == fonte) & (resto["palavra_chave"] == chave)]
        partes.append(grupo.sample(int(quantidade), random_state=SEMENTE))

    amostra = pd.concat(partes).sort_values(
        ["fonte", "palavra_chave", "data_publicacao"]
    )
    for coluna in COLUNAS_ROTULO:
        amostra[coluna] = ""
    return amostra[COLUNAS_V2].reset_index(drop=True)


def gerar_v2(destino: Path = ARQUIVO_PENDENTES_V2, sobrescrever: bool = False) -> Path:
    if destino.exists() and not sobrescrever:
        logger.warning("%s já existe; nada foi alterado (use --sobrescrever).", destino)
        return destino
    v1 = pd.read_csv(ARQUIVO_ROTULOS, sep=";", encoding="utf-8-sig", dtype={"id": str})
    amostra = selecionar_v2(dados.carregar_corpus(), set(v1["id"]))
    destino.parent.mkdir(parents=True, exist_ok=True)
    amostra.to_csv(destino, sep=";", index=False, encoding="utf-8-sig")
    logger.info("Planilha v2 com %d notícias gravada em %s", len(amostra), destino)
    logger.info(
        "Por fonte e palavra-chave:\n%s",
        amostra.groupby(["fonte", "palavra_chave"]).size().to_string(),
    )
    return destino


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(
        description="Gera a planilha de rótulos do benchmark."
    )
    parser.add_argument("--sobrescrever", action="store_true")
    parser.add_argument(
        "--v2", action="store_true", help="Planilha de pendentes do benchmark v2."
    )
    argumentos = parser.parse_args()
    if argumentos.v2:
        gerar_v2(sobrescrever=argumentos.sobrescrever)
    else:
        gerar(sobrescrever=argumentos.sobrescrever)
