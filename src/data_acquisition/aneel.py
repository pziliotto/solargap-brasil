"""
PROJETO: SolarGap Brasil
ARQUIVO: aneel.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 17/08/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Coleta da base de Micro e Mini Geração Distribuída (MMGD) - ANEEL.

FONTE:
    Portal de Dados Abertos da Aneel (CKAN).

DATASET:
    "Relação de empreendimentos de Mini e Micro Geração Distribuída"
    id: 5e0fafd2-21b9-4d5b-b622-40438d40aba2

OBS.:
    Arquivo vai vir em CSV compactado em ZIP ou parquet, será baixado
    em streaming, por isso esse módulo não reaproveita o requisitar() do
    coletor_base.

OBS2.:
    VPN precisa estar ativado e localizado no Brasil caso seja realizada a
    coleta enquanto fora do País.
"""

from __future__ import annotations

import logging
import time
import zipfile
from pathlib import Path

import requests

from src.data_acquisition.coletor_base import (
    calcular_espera_backoff,
    configurar_logging,
    obter_project_root,
)

PROJECT_ROOT = obter_project_root(__file__)
PASTA_RAW = PROJECT_ROOT / "data" / "raw"
PASTA_LOGS = PROJECT_ROOT / "logs"

BASE_ANEEL = "https://dadosabertos.aneel.gov.br"
DATASET_ID = "5e0fafd2-21b9-4d5b-b622-40438d40aba2"

# Troque para "parquet" para comparar tamanhos entre os dois formatos.
FORMATO = "zip"

RECURSOS = {
    "zip": {
        "resource_id": "b1bd71e7-d0ad-4214-9053-cbd58e9564a7",
        "nome_arquivo": "empreendimento-geracao-distribuida.zip",
    },
    "parquet": {
        "resource_id": "cd29f6eb-e08d-4db7-b6fb-ed6e3b682d27",
        "nome_arquivo": "empreendimento-geracao-distribuida.parquet",
    },
}

TIMEOUT = (30, 600)  # (conectar, ler)
TENTATIVAS = 4  # uma a mais que no IBGE — conexão internacional é instável
ESPERA_BASE = 5
CHUNK = 1024 * 256

# Colunas com dado pessoal identificável. Removidas da amostra porque o
# repositório é público e nenhum KPI do projeto depende delas (LGPD).
COLUNAS_SENSIVEIS = ["NumCPFCNPJ", "NomTitularEmpreendimento"]


def consultar_metadados() -> dict | None:
    """Consulta metadados do dataset sem baixar dado algum ('pergunte antes de puxar')."""
    url = f"{BASE_ANEEL}/api/3/action/package_show?id={DATASET_ID}"

    try:
        logging.info("Consultando metadados do dataset...")
        resposta = requests.get(url, timeout=(30, 60))
        resposta.raise_for_status()
        pacote = resposta.json()["result"]

        logging.info("Dataset: %s", pacote.get("title", "?"))
        for recurso in pacote.get("resources", []):
            tamanho = recurso.get("size")
            tamanho_txt = (
                f"{tamanho / (1024 * 1024):.1f} MB" if tamanho else "não informado"
            )
            logging.info(
                "  - %-16s | %-8s | %s",
                (recurso.get("format") or "?")[:16],
                tamanho_txt,
                recurso.get("name", "?")[:60],
            )

        return pacote

    except requests.exceptions.RequestException as erro:
        logging.warning("Não foi possível consultar metadados: %s", erro)
        return None


def montar_url_download(resource_id: str, nome_arquivo: str) -> str:
    return f"{BASE_ANEEL}/dataset/{DATASET_ID}/resource/{resource_id}/download/{nome_arquivo}"


def baixar_em_streaming(url: str, destino: Path) -> None:
    """Baixa o arquivo em blocos, gravando em .parcial até concluir."""
    ultimo_erro: Exception | None = None
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".parcial")

    for tentativa in range(1, TENTATIVAS + 1):
        try:
            logging.info("Baixando (tentativa %d/%d)...", tentativa, TENTATIVAS)

            with requests.get(url, timeout=TIMEOUT, stream=True) as resposta:
                resposta.raise_for_status()
                total = resposta.headers.get("Content-Length")
                if total:
                    logging.info(
                        "Tamanho informado: %.1f MB", int(total) / (1024 * 1024)
                    )

                baixado = 0
                marco = 0
                with open(temporario, "wb") as arquivo:
                    for bloco in resposta.iter_content(chunk_size=CHUNK):
                        if not bloco:
                            continue
                        arquivo.write(bloco)
                        baixado += len(bloco)
                        if baixado // (10 * 1024 * 1024) > marco:
                            marco = baixado // (10 * 1024 * 1024)
                            logging.info(
                                "  ... %.0f MB recebidos", baixado / (1024 * 1024)
                            )

            temporario.replace(destino)
            logging.info("Download concluído: %.2f MB", baixado / (1024 * 1024))
            return

        except requests.exceptions.RequestException as erro:
            ultimo_erro = erro
            logging.warning("Falha na tentativa %d: %s", tentativa, erro)
            temporario.unlink(missing_ok=True)

            if tentativa < TENTATIVAS:
                espera = calcular_espera_backoff(tentativa, ESPERA_BASE)
                logging.info("Aguardando %ds antes de nova tentativa...", espera)
                time.sleep(espera)

    logging.error("Todas as %d tentativas falharam.", TENTATIVAS)
    logging.error(
        "Se persistir (403/timeout), pode ser bloqueio geográfico — tente VPN com saída no Brasil."
    )
    raise ultimo_erro  # type: ignore[misc]


def inspecionar_zip(caminho: Path) -> None:
    """Lista o conteúdo do ZIP e o tamanho descomprimido, SEM extrair."""
    try:
        with zipfile.ZipFile(caminho) as z:
            total_descomprimido = 0
            for info in z.infolist():
                total_descomprimido += info.file_size
                logging.info(
                    "  - %-50s %.2f MB",
                    info.filename[:50],
                    info.file_size / (1024 * 1024),
                )

            comprimido = caminho.stat().st_size
            logging.info("Comprimido ..: %.2f MB", comprimido / (1024 * 1024))
            logging.info("Descomprimido: %.2f MB", total_descomprimido / (1024 * 1024))

    except zipfile.BadZipFile:
        logging.error(
            "Arquivo não é um ZIP válido — o servidor provavelmente devolveu uma página de erro."
        )
        raise


def baixar_mmgd() -> None:
    caminho_log = configurar_logging("ANEEL_MMGD", PASTA_LOGS)
    logging.info("=" * 70)
    logging.info("Coleta ANEEL — Empreendimentos de MMGD")
    logging.info("Raiz do projeto: %s", PROJECT_ROOT)
    logging.info("Formato escolhido: %s", FORMATO)

    consultar_metadados()

    recurso = RECURSOS[FORMATO]
    url = montar_url_download(recurso["resource_id"], recurso["nome_arquivo"])
    destino = PASTA_RAW / recurso["nome_arquivo"]

    try:
        baixar_em_streaming(url, destino)
    except requests.exceptions.RequestException:
        logging.error("Coleta abortada. Nenhum arquivo íntegro foi gravado.")
        raise

    if FORMATO == "zip":
        inspecionar_zip(destino)

    logging.info("Arquivo salvo em: %s", destino)
    logging.info("Log da sessão: %s", caminho_log)
    logging.info("Coleta concluída com sucesso.")
    logging.info("=" * 70)


if __name__ == "__main__":
    baixar_mmgd()
