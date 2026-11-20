"""
PROJETO: SolarGap Brasil
ARQUIVO: coletor_fatores.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 20/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Coleta as fontes dos fatores que explicam a taxa de realização do potencial
    solar municipal (TP4.5, Tarefa 3). Cada fonte vai para a camada Bronze
    (data/raw/), sem transformação, e não é baixada de novo se já estiver lá.

REGRA CENTRAL:
    Nenhum fator vem da MMGD (a base ANEEL de empreendimentos), para não vazar
    o alvo para o modelo. Até a ligação distribuidora -> município usa uma base
    oficial independente da MMGD (IndQual + DEC/FEC).

FONTES (registro completo em FONTES, abaixo):
    IBGE  - Censo 2022 (SIDRA 10295, 9923, 4714) e PIB dos Municípios 2023 (FTP)
    ANEEL - tarifas de aplicação, IndQual Município, DEC/FEC 2020-2029, IASC
    MapBiomas - Coleção 11, cobertura e uso da terra por município
    (ICMS/CONFAZ e irradiação NASA POWER já estão no projeto.)

OBS. DE USO:
    python -m src.data_acquisition.coletor_fatores
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

from src.data_acquisition.coletor_base import (
    calcular_espera_backoff,
    configurar_logging,
)
from src.potencial import config

USER_AGENT = "SolarGapBrasil/1.0 (projeto academico de ciencia de dados; INFNET)"
TIMEOUT = (15, 600)
TENTATIVAS = 3

SIDRA = "https://servicodados.ibge.gov.br/api/v3/agregados"
ANEEL = "https://dadosabertos.aneel.gov.br/dataset"
LICENCA_IBGE = (
    "Dados públicos do IBGE, uso livre com citação da fonte (Termo de uso do IBGE)"
)
LICENCA_ANEEL = "Open Data Commons Open Database License (ODbL)"

# nome -> metadados e destino do cache
FONTES: dict[str, dict] = {
    "renda": {
        "dataset": "IBGE, Censo 2022 — SIDRA 10295: rendimento nominal médio (13431) "
        "e mediano (13534) mensal domiciliar per capita, total",
        "url": f"{SIDRA}/10295/periodos/2022/variaveis/13431%7C13534"
        "?localidades=N6[all]&classificacao=2[6794]%7C86[95251]%7C58[95253]&view=flat",
        "ano": 2022,
        "licenca": LICENCA_IBGE,
        "arquivo": config.PASTA_RAW_IBGE / "renda_domiciliar_pc_municipio_2022.json",
    },
    "urbanizacao": {
        "dataset": "IBGE, Censo 2022 — SIDRA 9923: população residente (93) por "
        "situação do domicílio (urbana, rural, total)",
        "url": f"{SIDRA}/9923/periodos/2022/variaveis/93"
        "?localidades=N6[all]&classificacao=1[all]&view=flat",
        "ano": 2022,
        "licenca": LICENCA_IBGE,
        "arquivo": config.PASTA_RAW_IBGE / "populacao_situacao_municipio_2022.json",
    },
    "area_densidade": {
        "dataset": "IBGE, Censo 2022 — SIDRA 4714: população residente (93), área "
        "territorial (6318, km²) e densidade demográfica (614, hab/km²)",
        "url": f"{SIDRA}/4714/periodos/2022/variaveis/93%7C6318%7C614"
        "?localidades=N6[all]&view=flat",
        "ano": 2022,
        "licenca": LICENCA_IBGE,
        "arquivo": config.PASTA_RAW_IBGE
        / "populacao_area_densidade_municipio_2022.json",
    },
    "pib": {
        "dataset": "IBGE, PIB dos Municípios — base de dados 2010-2023 (FTP), VAB da "
        "agropecuária e VAB total. A publicação de 2022-2023 só traz PIB e PIB per "
        "capita; o VAB por atividade vai até 2021 (igual ao SIDRA 5938)",
        "url": "https://ftp.ibge.gov.br/Pib_Municipios/2022_2023/base/"
        "base_de_dados_2010_2023_xlsx.zip",
        "ano": 2021,
        "licenca": LICENCA_IBGE,
        "arquivo": config.PASTA_RAW_PIB / "base_de_dados_2010_2023_xlsx.zip",
    },
    "tarifas": {
        "dataset": "ANEEL — Tarifas de aplicação das distribuidoras de energia "
        "elétrica (TE e TUSD homologadas)",
        "url": f"{ANEEL}/5a583f3e-1646-4f67-bf0f-69db4203e89e/resource/"
        "9af99ef4-376a-4493-a075-5e48ab4da51b/download/"
        "tarifas-homologadas-distribuidoras-energia-eletrica.parquet",
        "ano": "vigências 2023-2025",
        "licenca": LICENCA_ANEEL,
        "arquivo": config.PASTA_RAW_ANEEL
        / "tarifas-homologadas-distribuidoras-energia-eletrica.parquet",
    },
    "indqual_municipio": {
        "dataset": "ANEEL — IndQual Município: ligação entre conjuntos elétricos de "
        "unidades consumidoras e municípios",
        "url": f"{ANEEL}/db9c9f60-b3b5-4504-9dfe-2637922d53ce/resource/"
        "3f841488-80a8-42f2-a6ca-e0c593b228de/download/indqual-municipio.csv",
        "ano": "gerado em 05/11/2026",
        "licenca": LICENCA_ANEEL,
        "arquivo": config.PASTA_RAW_ANEEL / "indqual-municipio.csv",
    },
    "dec_fec": {
        "dataset": "ANEEL — Indicadores coletivos de continuidade (DEC/FEC) "
        "2020-2029: conjunto elétrico -> distribuidora",
        "url": f"{ANEEL}/d5f0712e-62f6-4736-8dff-9991f10758a7/resource/"
        "d7f70fb1-725c-4748-afeb-65c6a78df550/download/"
        "indicadores-continuidade-coletivos-2020-2029.parquet",
        "ano": "conjuntos de 2023 em diante",
        "licenca": LICENCA_ANEEL,
        "arquivo": config.PASTA_RAW_ANEEL
        / "indicadores-continuidade-coletivos-2020-2029.parquet",
    },
    "iasc": {
        "dataset": "ANEEL — Índice ANEEL de Satisfação do Consumidor (IASC): "
        "classificação da distribuidora (concessionária ou permissionária)",
        "url": f"{ANEEL}/f216da23-4b7e-4bbe-9833-06905331a827/resource/"
        "7abd3a47-1e1a-4a33-933b-48d658a6f912/download/"
        "indice-aneel-satisfacao-consumidor.csv",
        "ano": "2022-2025",
        "licenca": LICENCA_ANEEL,
        "arquivo": config.PASTA_RAW_ANEEL / "indice-aneel-satisfacao-consumidor.csv",
    },
    "mapbiomas": {
        "dataset": "MapBiomas Brasil, Coleção 11 — cobertura e uso da terra (30 m), "
        "área por classe por bioma, estado e município, 1985-2025",
        "url": "https://drive.usercontent.google.com/download?"
        "id=1otOqymHuixvkRGVl65zTTNyfaHo46Gqk&export=download&confirm=t",
        "pagina": "https://brasil.mapbiomas.org/estatisticas/",
        "ano": 2023,
        "licenca": "CC BY 4.0 (uso público, aberto e gratuito mediante referência)",
        "arquivo": config.PASTA_RAW_MAPBIOMAS
        / "MAPBIOMAS_BRAZIL-COL.11-BIOME_STATE_MUNICIPALITY.zip",
    },
}

# Fontes já presentes no projeto (sem download nesta etapa)
FONTES_DO_PROJETO = {
    "icms": {
        "dataset": "CONFAZ — Convênio ICMS 16/15, adesão das UFs à isenção "
        "(data/processed/gold_icms_uf.csv, TP3)",
        "ano": "adesões 2015-2018; meses contados até 31/08/2026",
        "licenca": "Ato oficial, sem proteção autoral (Lei 9.610/98, art. 8º, IV)",
    },
    "irradiacao": {
        "dataset": "NASA POWER, ALLSKY_SFC_SW_DWN, média 2023-2025 (Tarefa 1, "
        "data/interim/potencial/irradiacao_municipal.parquet)",
        "ano": "2023-2025",
        "licenca": "Dados abertos da NASA, sem restrição de uso",
    },
}


def baixar(url: str, destino: Path) -> Path:
    """Baixa url para destino (atômico, com retry), se ainda não estiver no cache."""
    if destino.exists() and destino.stat().st_size > 0:
        logging.info("Em cache: %s", destino.name)
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".parcial")
    ultimo_erro: Exception | None = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            logging.info("Baixando (%d/%d): %s", tentativa, TENTATIVAS, url)
            with requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, stream=True
            ) as resposta:
                resposta.raise_for_status()
                tipo = resposta.headers.get("Content-Type", "")
                if "text/html" in tipo and destino.suffix not in (".html",):
                    raise ValueError(f"Resposta HTML inesperada ({tipo})")
                with open(temporario, "wb") as arquivo:
                    arquivo.writelines(resposta.iter_content(chunk_size=1 << 20))
            temporario.replace(destino)
            logging.info("Salvo: %s (%.1f MB)", destino, destino.stat().st_size / 1e6)
            return destino
        except (requests.exceptions.RequestException, ValueError) as erro:
            ultimo_erro = erro
            temporario.unlink(missing_ok=True)
            logging.warning("Falha: %s", erro)
            if tentativa < TENTATIVAS:
                time.sleep(calcular_espera_backoff(tentativa, 2))
    raise ultimo_erro  # type: ignore[misc]


def coletar_fatores() -> dict[str, Path]:
    configurar_logging("FATORES", config.PASTA_LOGS)
    caminhos = {}
    for nome, fonte in FONTES.items():
        caminhos[nome] = baixar(fonte["url"], fonte["arquivo"])
    return caminhos


if __name__ == "__main__":
    coletar_fatores()
