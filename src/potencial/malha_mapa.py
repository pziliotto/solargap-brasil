"""
PROJETO: SolarGap Brasil
ARQUIVO: potencial/malha_mapa.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Gera as malhas simplificadas usadas no mapa coroplético da página
    "Potencial Solar" (TP4.5, Tarefa 7): UFs e municípios do IBGE 2022, via
    geobr, em GeoJSON leve.

SAÍDAS (versionadas: referência de terceiros, IBGE):
    data/external/malhas/uf.geojson                  27 UFs, propriedade "uf"
    data/external/malhas/municipios/<UF>.geojson     um arquivo por UF,
                                                     propriedades "cod_ibge", "nome"

POR QUE SIMPLIFICAR E SEPARAR POR UF:
    A malha municipal completa tem dezenas de MB e travaria o navegador. Para
    um mapa de taxa por município, contornos com ~1 km de precisão bastam. A
    página só lê o arquivo da UF escolhida, então o mapa municipal abre rápido.

    Tolerância de simplificação (graus, com topologia preservada) e precisão
    das coordenadas:
        UF ......... 0,02° (~2 km), coordenadas com 2 casas
        município .. 0,005° (~500 m), coordenadas com 3 casas

OBS. DE USO:
    python -m src.potencial.malha_mapa
"""

from __future__ import annotations

import json
import logging

from src.data_acquisition.coletor_base import configurar_logging
from src.potencial import config

PASTA_MALHAS = config.PROJECT_ROOT / "data" / "external" / "malhas"
ARQUIVO_UF = PASTA_MALHAS / "uf.geojson"
PASTA_MUNICIPIOS = PASTA_MALHAS / "municipios"

TOLERANCIA_UF = 0.02
TOLERANCIA_MUNICIPIO = 0.005
CASAS_UF = 2
CASAS_MUNICIPIO = 3


def simplificar(geometrias, tolerancia: float, casas: int):
    """Simplifica preservando a topologia e arredonda as coordenadas."""
    import shapely

    simples = geometrias.simplify(tolerancia, preserve_topology=True)
    return simples.apply(
        lambda g: shapely.make_valid(shapely.set_precision(g, 10.0**-casas))
    )


def gravar_geojson(gdf, caminho, casas: int) -> int:
    """Grava o GeoDataFrame como GeoJSON compacto e devolve o tamanho em bytes."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = gdf.to_json(drop_id=True, to_wgs84=False)
    dados = json.loads(texto)
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return caminho.stat().st_size


def gerar() -> dict[str, int]:
    import geobr

    municipios = geobr.read_municipality(
        year=config.ANO_MALHA, simplified=True, show_progress=False
    )
    municipios = municipios.assign(
        cod_ibge=municipios["code_muni"].astype("int64").astype(str),
        nome=municipios["name_muni"].astype(str),
        uf=municipios["abbrev_state"].astype(str),
    )[["cod_ibge", "nome", "uf", "geometry"]]

    ufs = municipios[["uf", "geometry"]].dissolve(by="uf").reset_index()
    ufs["geometry"] = simplificar(ufs.geometry, TOLERANCIA_UF, CASAS_UF)
    tamanhos = {"uf": gravar_geojson(ufs, ARQUIVO_UF, CASAS_UF)}

    municipios["geometry"] = simplificar(
        municipios.geometry, TOLERANCIA_MUNICIPIO, CASAS_MUNICIPIO
    )
    for uf, grupo in municipios.groupby("uf"):
        tamanhos[uf] = gravar_geojson(
            grupo[["cod_ibge", "nome", "geometry"]],
            PASTA_MUNICIPIOS / f"{uf}.geojson",
            CASAS_MUNICIPIO,
        )
    return tamanhos


def main() -> None:
    configurar_logging("MALHA_MAPA", config.PROJECT_ROOT / "logs")
    tamanhos = gerar()
    logging.info(
        "Malhas: UF %.0f kB; municípios %.1f MB em %d arquivos (maior: %s, %.0f kB)",
        tamanhos["uf"] / 1e3,
        sum(v for k, v in tamanhos.items() if k != "uf") / 1e6,
        len(tamanhos) - 1,
        max((k for k in tamanhos if k != "uf"), key=tamanhos.get),
        max(v for k, v in tamanhos.items() if k != "uf") / 1e3,
    )


if __name__ == "__main__":
    main()
