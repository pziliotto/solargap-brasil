"""
PROJETO: SolarGap Brasil
ARQUIVO: potencial/malha_municipal.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 19/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Obtém a malha municipal de 2022 do IBGE (via geobr) e calcula UM ponto
    representativo por município, usado para consultar a irradiação na grade da
    NASA POWER.

SAÍDA:
    data/interim/potencial/municipios_pontos.parquet
        cod_ibge (str, 7 dígitos), nome, uf, lat, lon

DECISÕES:
    - representative_point() em vez de centroid: o centroide de um polígono
      côncavo ou em forma de "C" (municípios litorâneos, com ilhas ou de
      fronteira recortada) pode cair FORA do município — e até em outra célula
      da grade de irradiação. O ponto representativo é garantidamente interno.
    - Geometria simplificada (simplified=True, tolerância de 100 m): para um
      ponto interno numa grade de 1° (~110 km), a simplificação é irrelevante e
      o download é bem menor.
    - Coordenadas em SIRGAS 2000 (EPSG:4674), o CRS da malha. A diferença para
      WGS84, usado pela NASA POWER, é inferior a 1 m.

OBS. DE USO:
    python -m src.potencial.malha_municipal
"""

from __future__ import annotations

import logging

import pandas as pd

from src.data_acquisition.coletor_base import configurar_logging
from src.potencial import config

COLUNAS_PONTOS = ["cod_ibge", "nome", "uf", "lat", "lon"]


def obter_malha():
    """Baixa (ou lê do cache do geobr) a malha municipal do ano configurado."""
    import geobr  # import local: só este passo precisa da pilha geoespacial

    return geobr.read_municipality(
        year=config.ANO_MALHA, simplified=True, show_progress=False
    )


def calcular_pontos(malha) -> pd.DataFrame:
    """Transforma a malha (GeoDataFrame) na tabela de pontos representativos.

    Função pura, separada do download, para poder ser testada com polígonos
    sintéticos.
    """
    pontos = malha.geometry.representative_point()
    tabela = pd.DataFrame(
        {
            "cod_ibge": malha["code_muni"].astype("int64").astype(str),
            "nome": malha["name_muni"].astype(str),
            "uf": malha["abbrev_state"].astype(str),
            "lat": pontos.y.to_numpy(),
            "lon": pontos.x.to_numpy(),
        }
    )
    return tabela.sort_values("cod_ibge").reset_index(drop=True)


def validar_pontos(tabela: pd.DataFrame, malha=None) -> None:
    """Falha alto se a tabela não tiver os 5.570 municípios com código válido.

    Com a malha informada, confere também que cada ponto cai dentro do próprio
    polígono.
    """
    erros = []
    if len(tabela) != config.TOTAL_MUNICIPIOS:
        erros.append(f"{len(tabela)} municípios (esperado {config.TOTAL_MUNICIPIOS})")
    if tabela["cod_ibge"].duplicated().any():
        erros.append("códigos IBGE duplicados")
    if not tabela["cod_ibge"].str.fullmatch(r"\d{7}").all():
        erros.append("código IBGE fora do padrão de 7 dígitos")
    if tabela[["lat", "lon"]].isna().any().any():
        erros.append("coordenadas ausentes")
    if malha is not None:
        dentro = malha.geometry.contains(malha.geometry.representative_point())
        if not dentro.all():
            erros.append(f"{(~dentro).sum()} pontos fora do próprio polígono")
    if erros:
        raise ValueError("Malha municipal inválida: " + "; ".join(erros))


def construir_pontos() -> pd.DataFrame:
    """Executa o passo completo e grava o parquet de pontos."""
    configurar_logging("POTENCIAL_MALHA", config.PASTA_LOGS)
    logging.info("Lendo malha municipal %d via geobr...", config.ANO_MALHA)
    malha = obter_malha()
    tabela = calcular_pontos(malha)
    validar_pontos(tabela, malha)

    config.PASTA_INTERIM_POTENCIAL.mkdir(parents=True, exist_ok=True)
    tabela[COLUNAS_PONTOS].to_parquet(config.ARQUIVO_PONTOS, index=False)
    logging.info("%d pontos gravados em %s", len(tabela), config.ARQUIVO_PONTOS)
    return tabela


if __name__ == "__main__":
    construir_pontos()
