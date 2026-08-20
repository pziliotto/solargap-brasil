"""
PROJETO: SolarGap Brasil
ARQUIVO: coletor_base.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 17/08/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    - Funções genéricas e reutilizáveis pelos coletores de dados do projeto.
    - O módulo NÃO coleta dado nenhum sozinho, o que ele faz:
        - Descoberta de caminho;
        - Logging padronizado;
        - Requisição HTTP com retry;
        - Gravação da camada bronze (data/raw) em JSON

OBS. DE USO:
    Rodar como módulo no terminal
        python -m src.data_acquisition.ibge
        python -m src.data_acquisition.aneel
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import requests


def obter_project_root(arquivo: str, niveis_acima: int = 2) -> Path:
    """Deriva a raiz do projeto a partir da localização de um script.

    Pressupõe a estrutura <raiz>/src/data_acquisition/<script>.py
    ou seja, dois níveis acima do arquivo chamador. Se um coletor
    futuro morar em outra profundidade de pasta, ajustar "niveis_acima"
    na chamada.

    Lembrando que arquivo será chamado por <__file__>
    """
    return Path(arquivo).resolve().parents[niveis_acima]


def configurar_logging(fonte: str, pasta_logs: Path) -> Path:
    """Configura logging simultâneo em arquivo e console.

    'fonte' identifica a origem no nome do arquivo - por exemplo, 'IBGE_UF',
    'IBGE_MUNICIPIO', 'ANEEL_MMGD' - permitindo rastrear cada coleta
    separadamente, mesmo quando rodadas no mesmo dia.
    """
    pasta_logs.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_log = pasta_logs / f"{fonte}_{timestamp}.log"

    # Limpa handlers de uma chamada anterior nesse mesmo processo. Sem isso,
    # se dois coletores rodarem em sequência no mesmo script (ex.: um
    # orquestrador chamado IBGE e depois ANEEL), cada linha de log seria
    # escrita duas vezes - uma vez por handler acumulado.
    logging.getLogger().handlers.clear()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(caminho_log, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return caminho_log


def calcular_espera_backoff(tentativa: int, espera_base: int) -> int:
    """Calcula a espera (em segundos) antes da próxima tentativa.

    Dobra a cada tentativa: espera_base, 2x, 4x, 8x... ("backoff exponencial").
    Extraído como função própria por que a requisição JSON e o download da ANEEL
    precisam do mesmo cálculo.
    """
    return espera_base * (2 ** (tentativa - 1))


def requisitar(
    url: str,
    tentativas: int = 3,
    espera_base: int = 2,
    timeout: int | tuple[int, int] = 30,
) -> requests.Response:
    """Faz uma requisição GET com retry e espera progressia.

    Levanta a última exceção se todas as tentativas falharem - falhar alto é preferível
    a devolver uma resposta parcial ou vazia sem avisar quem chamou a função.
    """
    ultimo_erro: Exception | None = None

    for tentativa in range(1, tentativas + 1):
        try:
            logging.info(
                "Requisitando (tentativa %d/%d): %s", tentativa, tentativas, url
            )
            resposta = requests.get(url, timeout=timeout)
            resposta.raise_for_status()
            logging.info("Resposta recebida — status %d", resposta.status_code)
            return resposta

        except requests.exceptions.RequestException as erro:
            ultimo_erro = erro
            logging.warning("Falha na tentativa %d: %s", tentativa, erro)

            if tentativa < tentativas:
                espera = calcular_espera_backoff(tentativa, espera_base)
                logging.info("Arguadando %ds antes de nova tentativa...", espera)
                time.sleep(espera)

    logging.error("Todas as %d tentativas falharam.", tentativas)
    raise ultimo_erro  # type: ignore[misc]


def salvar_raw_json(payload, caminho: Path) -> None:
    """Grava tudo na camada Raw (data/raw) em JSON, sem transformação.

    ensure_ascii=False preserva acentuação legível (ex.: "Rondônia") ao
    abrir o arquivo em qualquer editor de texo
    """
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(payload, arquivo, ensure_ascii=False, indent=4)
