"""
PROJETO: SolarGap Brasil
ARQUIVO: coletor_nasa_power.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 19/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Coleta a irradiação solar mensal da NASA POWER para cada célula da grade
    que contém ao menos um município brasileiro (TP4.5 — Potencial solar).

CONSULTA:
    Endpoint:   https://power.larc.nasa.gov/api/temporal/monthly/point
    Parâmetro:  ALLSKY_SFC_SW_DWN — irradiação global horizontal em céu real
                ("All Sky Surface Shortwave Downward Irradiance")
    Comunidade: RE (Renewable Energy) -> unidade kWh/m²/dia ("kW-hr/m^2/day")
    Período:    config.ANOS_BASE (2023–2025), um valor por mês + média anual

GRADE (por que consultar por célula, e não por município):
    Os parâmetros solares do POWER têm resolução efetiva de 1° x 1° (CERES
    SYN1deg / FLASHFlux; ver config.RESOLUCAO_GRAUS_POWER). Dois municípios na
    mesma célula recebem exatamente a mesma série. Cada ponto é encaixado na
    célula (centro = floor(coordenada) + 0,5), as células são deduplicadas e
    cada uma é consultada UMA vez, pelo seu centro: ~5.570 municípios viram
    algumas centenas de requisições.

ESTRUTURA DA RESPOSTA (JSON, GeoJSON Feature):
    properties.parameter.ALLSKY_SFC_SW_DWN = {"202301": 4.91, ..., "202313": 4.87}
    Chave AAAAMM; MM = 13 é a média anual (ignorada aqui: recalculamos a média
    ponderada pelos dias). header.fill_value = -999.0 marca valor ausente.

CACHE (camada Bronze):
    Um JSON por célula em data/raw/nasa_power/, cópia fiel da resposta.
    Células já salvas e válidas não são baixadas de novo — o coletor pode ser
    interrompido e retomado. A gravação é atômica (arquivo .tmp + rename), para
    que uma interrupção não deixe JSON truncado no cache.

NAVEGAÇÃO EDUCADA:
    No máximo 4 requisições simultâneas, User-Agent do projeto, retry com
    backoff exponencial (calcular_espera_backoff) para falhas de rede, HTTP 429
    e 5xx. Outros 4xx indicam erro na consulta e falham sem nova tentativa.

OBS. DE USO:
    Requer data/interim/potencial/municipios_pontos.parquet:
        python -m src.potencial.malha_municipal
        python -m src.data_acquisition.coletor_nasa_power
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

from src.data_acquisition.coletor_base import (
    calcular_espera_backoff,
    configurar_logging,
)
from src.potencial import config

URL_BASE = "https://power.larc.nasa.gov/api/temporal/monthly/point"
PARAMETRO = "ALLSKY_SFC_SW_DWN"
COMUNIDADE = "RE"
VALOR_PREENCHIMENTO = -999.0

USER_AGENT = "SolarGapBrasil/1.0 (projeto academico de ciencia de dados; INFNET)"
MAX_SIMULTANEAS = 4
TENTATIVAS = 5
ESPERA_BASE = 2
TIMEOUT = (10, 90)

# Status HTTP que justificam nova tentativa: limite de taxa e erros do servidor.
STATUS_RETENTAVEIS = {429, 500, 502, 503, 504}


# ═══════════════════ Grade ═══════════════════


def encaixar_na_grade(
    coordenada: float, resolucao: float = config.RESOLUCAO_GRAUS_POWER
) -> float:
    """Devolve o centro da célula da grade que contém a coordenada.

    Bordas em múltiplos da resolução; centro no meio da célula. Para 1°:
    -22,1 -> -22,5; -22,0 -> -21,5 (a borda pertence à célula de cima, como o
    próprio POWER faz). O round final elimina resíduo de ponto flutuante.
    """
    return round(math.floor(coordenada / resolucao) * resolucao + resolucao / 2, 4)


def id_celula(lat_centro: float, lon_centro: float) -> str:
    """Identificador textual da célula, usado na Silver e no nome do cache."""
    return f"lat{lat_centro:.1f}_lon{lon_centro:.1f}"


def atribuir_celulas(pontos: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta lat_celula, lon_celula e celula_power à tabela de pontos."""
    resultado = pontos.copy()
    resultado["lat_celula"] = resultado["lat"].map(encaixar_na_grade)
    resultado["lon_celula"] = resultado["lon"].map(encaixar_na_grade)
    resultado["celula_power"] = [
        id_celula(la, lo)
        for la, lo in zip(resultado["lat_celula"], resultado["lon_celula"])
    ]
    return resultado


def celulas_unicas(pontos_com_celula: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por célula distinta, com o número de municípios que ela cobre."""
    return (
        pontos_com_celula.groupby(
            ["celula_power", "lat_celula", "lon_celula"], as_index=False
        )
        .size()
        .rename(columns={"size": "n_municipios"})
        .sort_values("celula_power")
        .reset_index(drop=True)
    )


# ═══════════════════ Cache Bronze ═══════════════════


def caminho_cache(
    celula: str, anos: tuple[int, ...] = config.ANOS_BASE, pasta: Path | None = None
) -> Path:
    """Arquivo da célula no cache. O período entra no nome para que uma mudança
    em ANOS_BASE nunca reaproveite uma série de outro intervalo."""
    pasta = pasta or config.PASTA_RAW_POWER
    return pasta / f"{celula}_{min(anos)}_{max(anos)}.json"


def payload_valido(payload: dict, anos: tuple[int, ...] = config.ANOS_BASE) -> bool:
    """Confere se a resposta tem a série do parâmetro para todos os meses pedidos.

    Valores -999 são aceitos aqui (são ausência legítima, tratada na Silver); o
    que se rejeita é a estrutura incompleta, sinal de resposta de erro.
    """
    try:
        serie = payload["properties"]["parameter"][PARAMETRO]
    except (KeyError, TypeError):
        return False
    return all(f"{ano}{mes:02d}" in serie for ano in anos for mes in range(1, 13))


def ler_cache(caminho: Path, anos: tuple[int, ...] = config.ANOS_BASE) -> dict | None:
    """Lê a célula do cache; None se não existe ou está inválida."""
    if not caminho.exists():
        return None
    try:
        payload = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logging.warning("Cache ilegível, será baixado de novo: %s", caminho.name)
        return None
    return payload if payload_valido(payload, anos) else None


def gravar_cache(payload: dict, caminho: Path) -> None:
    """Grava atomicamente: escreve num .tmp e renomeia por cima."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".json.tmp")
    temporario.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporario.replace(caminho)


# ═══════════════════ Requisição ═══════════════════

_local = threading.local()


def _sessao() -> requests.Session:
    """Uma sessão por thread: requests.Session não é garantidamente thread-safe."""
    if not hasattr(_local, "sessao"):
        _local.sessao = requests.Session()
        _local.sessao.headers["User-Agent"] = USER_AGENT
    return _local.sessao


def montar_parametros(
    lat: float, lon: float, anos: tuple[int, ...] = config.ANOS_BASE
) -> dict:
    return {
        "parameters": PARAMETRO,
        "community": COMUNIDADE,
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "start": str(min(anos)),
        "end": str(max(anos)),
        "format": "JSON",
    }


def baixar_celula(
    lat: float, lon: float, anos: tuple[int, ...] = config.ANOS_BASE
) -> dict:
    """Consulta o POWER para o centro de uma célula, com retry e backoff.

    Levanta a última exceção se todas as tentativas falharem.
    """
    parametros = montar_parametros(lat, lon, anos)
    ultimo_erro: Exception | None = None

    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resposta = _sessao().get(URL_BASE, params=parametros, timeout=TIMEOUT)
            if resposta.status_code in STATUS_RETENTAVEIS:
                raise requests.exceptions.HTTPError(
                    f"HTTP {resposta.status_code}", response=resposta
                )
            resposta.raise_for_status()  # demais 4xx: erro da consulta, sem retry
            payload = resposta.json()
            if not payload_valido(payload, anos):
                raise ValueError(f"Resposta sem a série completa de {PARAMETRO}")
            return payload

        except requests.exceptions.HTTPError as erro:
            status = erro.response.status_code if erro.response is not None else None
            if status is not None and status not in STATUS_RETENTAVEIS:
                raise
            ultimo_erro = erro
        except (requests.exceptions.RequestException, ValueError) as erro:
            ultimo_erro = erro

        logging.warning(
            "Célula (%.1f, %.1f) — falha %d/%d: %s",
            lat,
            lon,
            tentativa,
            TENTATIVAS,
            ultimo_erro,
        )
        if tentativa < TENTATIVAS:
            time.sleep(calcular_espera_backoff(tentativa, ESPERA_BASE))

    raise ultimo_erro  # type: ignore[misc]


def obter_celula(
    celula: str, lat: float, lon: float, anos: tuple[int, ...] = config.ANOS_BASE
) -> str:
    """Garante a célula no cache. Devolve 'cache' ou 'baixada'."""
    caminho = caminho_cache(celula, anos)
    if ler_cache(caminho, anos) is not None:
        return "cache"
    payload = baixar_celula(lat, lon, anos)
    gravar_cache(payload, caminho)
    return "baixada"


def coletar_celulas(
    celulas: pd.DataFrame, max_simultaneas: int = MAX_SIMULTANEAS
) -> dict[str, int]:
    """Baixa em paralelo (limitado) todas as células ausentes do cache.

    Falhas individuais são registradas e contadas; a função levanta erro no
    fim se alguma célula ficou sem dado, para a Silver nunca rodar incompleta.
    """
    contagem = {"cache": 0, "baixada": 0, "falha": 0}
    total = len(celulas)

    with ThreadPoolExecutor(max_workers=max_simultaneas) as executor:
        futuros = {
            executor.submit(obter_celula, c.celula_power, c.lat_celula, c.lon_celula): c
            for c in celulas.itertuples()
        }
        for i, futuro in enumerate(as_completed(futuros), start=1):
            celula = futuros[futuro].celula_power
            try:
                contagem[futuro.result()] += 1
            except Exception as erro:  # noqa: BLE001 — registrar e seguir
                contagem["falha"] += 1
                logging.error("Célula %s falhou: %s", celula, erro)
            if i % 50 == 0 or i == total:
                logging.info("Progresso: %d/%d células — %s", i, total, contagem)

    if contagem["falha"]:
        raise RuntimeError(
            f"{contagem['falha']} célula(s) sem dado; rode de novo para retomar."
        )
    return contagem


# ═══════════════════ Orquestração ═══════════════════


def coletar_nasa_power() -> dict[str, int]:
    """Lê os pontos municipais, deduplica as células e coleta as ausentes."""
    caminho_log = configurar_logging("NASA_POWER", config.PASTA_LOGS)
    inicio = time.perf_counter()

    if not config.ARQUIVO_PONTOS.exists():
        raise FileNotFoundError(
            f"{config.ARQUIVO_PONTOS} não encontrado. "
            "Rode antes: python -m src.potencial.malha_municipal"
        )
    pontos = atribuir_celulas(pd.read_parquet(config.ARQUIVO_PONTOS))
    celulas = celulas_unicas(pontos)
    logging.info(
        "%d municípios em %d células de %.0f° (%s a %s)",
        len(pontos),
        len(celulas),
        config.RESOLUCAO_GRAUS_POWER,
        min(config.ANOS_BASE),
        max(config.ANOS_BASE),
    )

    contagem = coletar_celulas(celulas)
    duracao = time.perf_counter() - inicio
    logging.info(
        "Coleta concluída em %.1fs — %d baixadas, %d do cache. Log: %s",
        duracao,
        contagem["baixada"],
        contagem["cache"],
        caminho_log,
    )
    return {**contagem, "celulas": len(celulas), "segundos": round(duracao, 1)}


if __name__ == "__main__":
    coletar_nasa_power()
