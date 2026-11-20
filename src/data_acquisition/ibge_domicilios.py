"""
PROJETO: SolarGap Brasil
ARQUIVO: ibge_domicilios.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 19/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Coleta o número de domicílios particulares permanentes ocupados por
    município, do Censo Demográfico 2022 (TP4.5 — Potencial solar municipal).
    É a base do potencial técnico: cada domicílio ocupado contribui com um
    telhado típico (config.AREA_UTIL_TELHADO_M2).

TABELA SIDRA: 4712 — "Domicílios particulares permanentes ocupados, Moradores
              em domicílios particulares permanentes ocupados e Média de
              moradores em domicílios particulares permanentes ocupados"
VARIÁVEL:     381 — "Domicílios particulares permanentes ocupados" (Domicílios)
NÍVEL:        N6 (Município), período 2022
URL:          https://servicodados.ibge.gov.br/api/v3/agregados/4712/periodos/2022/variaveis/381?localidades=N6[all]&view=flat
PÁGINA:       https://sidra.ibge.gov.br/tabela/4712

POR QUE A 4712:
    A tabela 9922 traz a mesma variável 381 desagregada por situação do
    domicílio (urbana/rural); para o total municipal as duas coincidem, e a
    4712 não exige escolher categoria de classificação.
    "Particulares permanentes ocupados" exclui domicílios coletivos (hotéis,
    presídios), improvisados e vagos/de uso ocasional — é o universo de casas
    com morador que poderiam instalar geração no próprio telhado.

CACHE (camada Bronze):
    data/raw/ibge/domicilios_municipio_2022.json — resposta view=flat sem
    transformação. Se já existir, não é baixado de novo.

OBS. DE USO:
    python -m src.data_acquisition.ibge_domicilios
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from src.data_acquisition.coletor_base import (
    configurar_logging,
    obter_project_root,
    requisitar,
    salvar_raw_json,
)

PROJECT_ROOT = obter_project_root(__file__)
PASTA_RAW_IBGE = PROJECT_ROOT / "data" / "raw" / "ibge"
PASTA_LOGS = PROJECT_ROOT / "logs"

TABELA_SIDRA = 4712
VARIAVEL_SIDRA = 381
URL_SIDRA = (
    f"https://servicodados.ibge.gov.br/api/v3/agregados/{TABELA_SIDRA}"
    f"/periodos/2022/variaveis/{VARIAVEL_SIDRA}?localidades=N6[all]&view=flat"
)
ARQUIVO_DOMICILIOS = PASTA_RAW_IBGE / "domicilios_municipio_2022.json"
TOTAL_MUNICIPIOS = 5570


def baixar_domicilios(caminho: Path = ARQUIVO_DOMICILIOS) -> Path:
    """Baixa a tabela para o cache Bronze, se ainda não estiver lá."""
    if caminho.exists():
        logging.info("Domicílios já em cache: %s", caminho)
        return caminho
    resposta = requisitar(URL_SIDRA, timeout=(10, 120))
    salvar_raw_json(resposta.json(), caminho)
    logging.info("Domicílios salvos em %s", caminho)
    return caminho


def ler_domicilios(caminho: Path = ARQUIVO_DOMICILIOS) -> pd.DataFrame:
    """Converte o JSON view=flat em (cod_ibge, domicilios).

    O primeiro registro do view=flat é a legenda. A chave do código do
    município é localizada pelo texto da legenda (mesma regra de
    construir_silver.ler_ibge_flat), sem fixar D1C/D3C no código.
    """
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    legenda, registros = dados[0], dados[1:]
    chave_codigo = next(
        (k for k, v in legenda.items() if v == "Município (Código)"), None
    )
    if chave_codigo is None or "V" not in legenda:
        raise ValueError(f"Legenda do SIDRA sem as chaves esperadas: {legenda}")

    tabela = pd.DataFrame(registros)
    resultado = pd.DataFrame(
        {
            "cod_ibge": tabela[chave_codigo].astype(str).str.strip(),
            # "-" ou "..." no SIDRA = sem dado; vira NaN e é barrado na validação
            "domicilios": pd.to_numeric(tabela["V"], errors="coerce"),
        }
    )
    validar_domicilios(resultado)
    resultado["domicilios"] = resultado["domicilios"].astype("int64")
    return resultado.sort_values("cod_ibge").reset_index(drop=True)


def validar_domicilios(tabela: pd.DataFrame) -> None:
    erros = []
    if len(tabela) != TOTAL_MUNICIPIOS:
        erros.append(f"{len(tabela)} municípios (esperado {TOTAL_MUNICIPIOS})")
    if tabela["cod_ibge"].duplicated().any():
        erros.append("códigos duplicados")
    if tabela["domicilios"].isna().any():
        erros.append(f"{tabela['domicilios'].isna().sum()} municípios sem valor")
    if (tabela["domicilios"] <= 0).any():
        erros.append("municípios com zero domicílios")
    if erros:
        raise ValueError("Domicílios SIDRA inválidos: " + "; ".join(erros))


def coletar_domicilios() -> pd.DataFrame:
    configurar_logging("IBGE_DOMICILIOS", PASTA_LOGS)
    logging.info("SIDRA tabela %d, variável %d", TABELA_SIDRA, VARIAVEL_SIDRA)
    tabela = ler_domicilios(baixar_domicilios())
    logging.info(
        "%d municípios | %s domicílios particulares permanentes ocupados",
        len(tabela),
        f"{tabela['domicilios'].sum():,}".replace(",", "."),
    )
    return tabela


if __name__ == "__main__":
    coletar_domicilios()
