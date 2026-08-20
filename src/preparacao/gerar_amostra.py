"""
PROJETO: SolarGap Brasil
ARQUIVO: gerar_amostra.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 19/08/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    - Gera uma pequena amostra estratificada da base MMGD da ANEEL, para ser
    versionada no Git e utilizada na demo do streamlit para primeira visualização.

NECESSIDADE:
    - O ZIP da ANEEl possui ~105 MB e o CSV interno passa de 1.4 GB - acima do limite
    de 100 MB do GitHub.
    - A base foi retirada do versionamento e a amostra foi colocada no lugar.

ESTRATIFICADA vs HEAD:
    - Dado uma possível ordenação nos dados da base e o foco na disparidade entre unidades
    federativas do país, garantimos uma representação similar de cada estado na amostra.

CSV vs PARQUET:
    - A base será versionada em CSV por conta da renderização do Github para inspeção
    de terceiros (professor, recrutador, etc)

OBS. DE USO:
    Rodar como módulo no terminal a partir da raiz
        python -m src.preparacao.gerar_amostra
"""

from __future__ import annotations

import logging
import sys
import zipfile
from pathlib import Path

import pandas as pd

from src.data_acquisition.coletor_base import configurar_logging, obter_project_root

PROJECT_ROOT = obter_project_root(__file__)
PASTA_RAW = PROJECT_ROOT / "data" / "raw"
PASTA_LOGS = PROJECT_ROOT / "logs"

ARQUIVO_ZIP = PASTA_RAW / "empreendimento-geracao-distribuida.zip"
ARQUIVO_AMOSTRA = PASTA_RAW / "amostra_mmgd.csv"

LINHAS_POR_UF = 40  # 40 x 27 UFs = ~1080 linhas
TAMANHO_CHUNK = 200_000  # linhas lidas por vez
SEPARADOR = ";"  # padrão em bases governamentais brasileiras
ENCODINGS = ["utf-8", "latin-1"]  # tentados nesta ordem

COLUNA_UF = "SigUF"

# Colunas com dado pessoal identificável. Removidas da amostra porque o
# repositório é público e nenhum KPI do projeto depende delas (LGPD).
COLUNAS_SENSIVEIS = ["NumCPFCNPJ", "NomTitularEmpreendimento"]


def localizar_csv_no_zip(caminho_zip: Path) -> str:
    """Descobre o nome do CSV dentro do ZIP, sem extrair nada."""
    if not caminho_zip.exists():
        logging.error("Arquivo não encontrado: %s", caminho_zip)
        logging.error("Rode antes: python -m src.data_acquisition.aneel")
        sys.exit(1)

    with zipfile.ZipFile(caminho_zip) as arquivo_zip:
        conteudo = arquivo_zip.infolist()

        logging.info("Conteúdo do ZIP:")
        for info in conteudo:
            logging.info(
                "  %-45s %8.1f MB", info.filename[:45], info.file_size / (1024 * 1024)
            )

        candidatos = [
            i.filename for i in conteudo if i.filename.lower().endswith(".csv")
        ]

    if not candidatos:
        logging.error("Nenhum CSV encontrado dentro do ZIP.")
        sys.exit(1)

    if len(candidatos) > 1:
        logging.warning("Mais de um CSV no ZIP; usando o primeiro: %s", candidatos[0])

    return candidatos[0]


def abrir_leitor(caminho_zip: Path, nome_csv: str, encoding: str):
    """Devolve um leitor em chunks do CSV interno, sem extrair o ZIP."""
    arquivo_zip = zipfile.ZipFile(caminho_zip)
    fluxo = arquivo_zip.open(nome_csv)

    return pd.read_csv(
        fluxo,
        sep=SEPARADOR,
        encoding=encoding,
        dtype=str,
        chunksize=TAMANHO_CHUNK,
        on_bad_lines="warn",
    )


def coletar_amostra_estratificada(caminho_zip: Path, nome_csv: str) -> pd.DataFrame:
    """Percorre o CSV em chunks, acumulando até N linhas por UF."""
    ultimo_erro: Exception | None = None

    for encoding in ENCODINGS:
        logging.info("Tentando leitura com encoding '%s'...", encoding)
        acumulado: dict[str, list[pd.DataFrame]] = {}
        contagem: dict[str, int] = {}

        try:
            leitor = abrir_leitor(caminho_zip, nome_csv, encoding)

            for numero, chunk in enumerate(leitor, start=1):
                if numero == 1:
                    logging.info("Colunas detectadas (%d):", len(chunk.columns))
                    for coluna in chunk.columns:
                        logging.info("  - %s", coluna)

                    if COLUNA_UF not in chunk.columns:
                        logging.error("Coluna '%s' não existe no arquivo.", COLUNA_UF)
                        sys.exit(1)

                for uf, grupo in chunk.groupby(COLUNA_UF, observed=True):
                    atual = contagem.get(uf, 0)
                    if atual >= LINHAS_POR_UF:
                        continue

                    faltam = LINHAS_POR_UF - atual
                    acumulado.setdefault(uf, []).append(grupo.head(faltam))
                    contagem[uf] = atual + min(faltam, len(grupo))

                if numero % 5 == 0:
                    completas = sum(1 for n in contagem.values() if n >= LINHAS_POR_UF)
                    linhas_lidas = numero * TAMANHO_CHUNK
                    logging.info(
                        "  chunk %d (~%s linhas) — %d UFs com cota completa",
                        numero,
                        f"{linhas_lidas:,}".replace(",", "."),
                        completas,
                    )

            break  # leitura concluída sem erro de encoding

        except UnicodeDecodeError as erro:
            ultimo_erro = erro
            logging.warning("Encoding '%s' falhou: %s", encoding, erro)
            continue

    else:
        logging.error("Nenhum encoding funcionou. Último erro: %s", ultimo_erro)
        sys.exit(1)

    if not acumulado:
        logging.error("Nenhum registro coletado. O arquivo está vazio?")
        sys.exit(1)

    partes = [df for grupos in acumulado.values() for df in grupos]
    amostra = pd.concat(partes, ignore_index=True).sort_values(COLUNA_UF)

    logging.info("--- Cobertura por UF ---")
    for uf in sorted(contagem):
        marca = "ok" if contagem[uf] >= LINHAS_POR_UF else "PARCIAL"
        logging.info("  %-4s %4d linhas  (%s)", uf, contagem[uf], marca)

    logging.info("UFs representadas: %d", len(contagem))
    if len(contagem) < 27:
        logging.warning("Menos de 27 UFs na amostra — investigue antes de usar.")

    return amostra


def remover_dados_pessoais(amostra: pd.DataFrame) -> pd.DataFrame:
    """Descarta colunas com dado pessoal antes da publicação no repositório."""
    presentes = [c for c in COLUNAS_SENSIVEIS if c in amostra.columns]

    if presentes:
        logging.info("Removendo colunas com dado pessoal: %s", presentes)
        amostra = amostra.drop(columns=presentes)
    else:
        logging.info("Nenhuma coluna sensível encontrada.")

    return amostra


def salvar_amostra(amostra: pd.DataFrame, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    amostra.to_csv(destino, index=False, sep=SEPARADOR, encoding="utf-8")

    tamanho_kb = destino.stat().st_size / 1024
    logging.info("Amostra salva: %s", destino)
    logging.info("Linhas ......: %d", len(amostra))
    logging.info("Colunas .....: %d", len(amostra.columns))
    logging.info("Tamanho .....: %.1f KB", tamanho_kb)

    if tamanho_kb > 5 * 1024:
        logging.warning("Amostra acima de 5 MB — considere reduzir LINHAS_POR_UF.")


def gerar_amostra() -> None:
    caminho_log = configurar_logging("AMOSTRA_MMGD", PASTA_LOGS)
    logging.info("=" * 70)
    logging.info("Geração de amostra estratificada — MMGD/ANEEL")
    logging.info("Raiz do projeto: %s", PROJECT_ROOT)

    nome_csv = localizar_csv_no_zip(ARQUIVO_ZIP)
    logging.info("CSV selecionado: %s", nome_csv)

    amostra = coletar_amostra_estratificada(ARQUIVO_ZIP, nome_csv)
    amostra = remover_dados_pessoais(amostra)
    salvar_amostra(amostra, ARQUIVO_AMOSTRA)

    logging.info("Log da sessão: %s", caminho_log)
    logging.info("Concluído.")
    logging.info("=" * 70)


if __name__ == "__main__":
    gerar_amostra()
