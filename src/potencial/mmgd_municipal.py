"""
PROJETO: SolarGap Brasil
ARQUIVO: potencial/mmgd_municipal.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 19/11/2026
ATUALIZAÇÃO: 20/11/2026 — lê a Silver (que passou a ter modalidade, distribuidora
             e a potência corrigida dos registros de 75 kW suspeitos) em vez do
             ZIP; três visões de potência por município

DESCRIÇÃO:
    Agrega a MMGD solar por município (código IBGE de 7 dígitos), com
    detalhamento por classe de consumo e por modalidade.

ENTRADA:
    data/interim/mmgd_silver.parquet, fonte = "Radiação solar". A Silver já traz
    limpeza, exclusões (ano 1900, anteriores a 2012, potência <= 0), correções
    de código municipal e UF, fonte imputada e o tratamento da potência
    suspeita (construir_silver.py e potencia_suspeita.py). Sem colunas
    pessoais (LGPD).

VISÕES DE POTÊNCIA (mesmo padrão do painel):
    kwp_*               visão corrigida (padrão): todos os registros,
                        potencia_corrigida_kw
    kwp_*_aneel         critério ANEEL: sem registros de fonte imputada,
                        potência oficial (potencia_kw)
    kwp_*_conservadora  limite conservador: só os residenciais de 75 kW
                        suspeitos são corrigidos (potencia_conservadora_kw)

    MdaPotenciaInstaladaKW está em kW; para centrais fotovoltaicas a ANEEL
    registra a menor entre a potência dos módulos e a dos inversores. Tratamos
    como kWp; se o inversor limita, y fica levemente subestimado.

SAÍDA:
    data/interim/potencial/mmgd_municipal.parquet — um registro por município
    com MMGD solar: cod_ibge, uf, kwp_total(+_aneel, +_conservadora),
    n_unidades, n_potencia_suspeita, kwp_local_res_rural(+_aneel,
    +_conservadora), n_local_res_rural, kwp_classe_<classe>...,
    kwp_mod_<modalidade>... (detalhes na visão corrigida)

OBS. DE USO:
    python -m src.potencial.mmgd_municipal      (requer construir_silver)
"""

from __future__ import annotations

import logging
import re
import unicodedata

import pandas as pd

from src.data_acquisition.coletor_base import configurar_logging
from src.potencial import config
from src.preparacao import esquema

ARQUIVO_SILVER_MMGD = config.PROJECT_ROOT / "data" / "interim" / "mmgd_silver.parquet"
COLUNAS_SILVER = [
    "cod_municipio",
    "sigla_uf",
    "classe_consumo",
    "modalidade",
    "fonte_imputada",
    "flag_potencia_suspeita",
    "potencia_kw",
    "potencia_corrigida_kw",
    "potencia_conservadora_kw",
]
CHAVES = ["cod_ibge", "uf", "classe_consumo", "modalidade"]
SEM_INFORMACAO = "nao_informada"

# Sufixo da coluna -> medida do resumo (kWp por visão)
VISOES = {"": "kwp", "_aneel": "kwp_aneel", "_conservadora": "kwp_conservadora"}


def normalizar_rotulo(texto: str | None) -> str:
    """'Poder Público' -> 'poder_publico'; nulo -> 'nao_informada'."""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)) or texto is pd.NA:
        return SEM_INFORMACAO
    sem_acento = (
        unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    )
    rotulo = re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")
    return rotulo or SEM_INFORMACAO


def rotulo_modalidade(texto: str | None) -> str:
    """Nome curto da modalidade (config.MODALIDADES_ANEEL) ou o texto normalizado."""
    if isinstance(texto, str) and texto.strip() in config.MODALIDADES_ANEEL:
        return config.MODALIDADES_ANEEL[texto.strip()]
    return normalizar_rotulo(texto)


# ═══════════════════ Agregação (funções puras) ═══════════════════


def resumir_registros(registros: pd.DataFrame) -> pd.DataFrame:
    """Soma kWp (nas três visões) e conta unidades por município x UF x classe
    x modalidade.

    Entrada: um registro por empreendimento, com as colunas de COLUNAS_SILVER.
    """
    oficial = registros["potencia_kw"].astype("float64")
    df = pd.DataFrame(
        {
            "cod_ibge": registros["cod_municipio"].astype("Int64").astype(str),
            "uf": registros["sigla_uf"],
            "classe_consumo": registros["classe_consumo"].map(normalizar_rotulo),
            "modalidade": registros["modalidade"].map(rotulo_modalidade),
            "kwp": registros["potencia_corrigida_kw"].astype("float64"),
            "kwp_aneel": oficial.where(~registros["fonte_imputada"].astype(bool), 0.0),
            "kwp_conservadora": registros["potencia_conservadora_kw"].astype("float64"),
            "n_suspeita": registros["flag_potencia_suspeita"].astype(int),
        }
    )
    return df.groupby(CHAVES, as_index=False, dropna=False).agg(
        kwp=("kwp", "sum"),
        kwp_aneel=("kwp_aneel", "sum"),
        kwp_conservadora=("kwp_conservadora", "sum"),
        n=("kwp", "size"),
        n_suspeita=("n_suspeita", "sum"),
    )


def eh_local_res_rural(classe: pd.Series, modalidade: pd.Series) -> pd.Series:
    """Máscara da métrica principal: Residencial/Rural com geração na própria UC."""
    classes = {normalizar_rotulo(c) for c in config.CLASSES_PRINCIPAIS}
    return classe.isin(classes) & (
        modalidade == rotulo_modalidade(config.MODALIDADE_PRINCIPAL)
    )


def consolidar(resumo: pd.DataFrame) -> pd.DataFrame:
    """Do resumo longo para uma linha por município (colunas largas)."""
    medidas = list(VISOES.values()) + ["n", "n_suspeita"]
    resumo = resumo.groupby(CHAVES, as_index=False, dropna=False)[medidas].sum()

    base = resumo.groupby(["cod_ibge", "uf"], as_index=False).agg(
        n_unidades=("n", "sum"),
        n_potencia_suspeita=("n_suspeita", "sum"),
        **{f"kwp_total{suf}": (medida, "sum") for suf, medida in VISOES.items()},
    )

    local = resumo[eh_local_res_rural(resumo["classe_consumo"], resumo["modalidade"])]
    local = local.groupby("cod_ibge").agg(
        n_local_res_rural=("n", "sum"),
        **{
            f"kwp_local_res_rural{suf}": (medida, "sum")
            for suf, medida in VISOES.items()
        },
    )

    por_classe = resumo.pivot_table(
        index="cod_ibge", columns="classe_consumo", values="kwp", aggfunc="sum"
    ).add_prefix("kwp_classe_")
    por_modalidade = resumo.pivot_table(
        index="cod_ibge", columns="modalidade", values="kwp", aggfunc="sum"
    ).add_prefix("kwp_mod_")

    resultado = (
        base.set_index("cod_ibge")
        .join([local, por_classe, por_modalidade])
        .fillna(0)
        .reset_index()
    )
    for coluna in ("n_unidades", "n_potencia_suspeita", "n_local_res_rural"):
        resultado[coluna] = resultado[coluna].astype("int64")
    colunas_fixas = (
        ["cod_ibge", "uf"]
        + [f"kwp_total{suf}" for suf in VISOES]
        + ["n_unidades", "n_potencia_suspeita"]
        + [f"kwp_local_res_rural{suf}" for suf in VISOES]
        + ["n_local_res_rural"]
    )
    detalhe = sorted(c for c in resultado.columns if c not in colunas_fixas)
    return (
        resultado[colunas_fixas + detalhe]
        .sort_values("cod_ibge")
        .reset_index(drop=True)
    )


# ═══════════════════ Execução ═══════════════════


def ler_solar_silver() -> pd.DataFrame:
    return pd.read_parquet(
        ARQUIVO_SILVER_MMGD,
        columns=COLUNAS_SILVER,
        filters=[("fonte_geracao", "==", esquema.FONTE_SOLAR)],
    )


def construir_mmgd_municipal() -> pd.DataFrame:
    configurar_logging("POTENCIAL_MMGD", config.PASTA_LOGS)
    logging.info("Lendo Silver: %s", ARQUIVO_SILVER_MMGD.name)
    solar = ler_solar_silver()
    sem_municipio = int(solar["cod_municipio"].isna().sum())
    tabela = consolidar(resumir_registros(solar[solar["cod_municipio"].notna()]))

    logging.info(
        "Solares %d | sem município %d | municípios com MMGD solar %d",
        len(solar),
        sem_municipio,
        len(tabela),
    )
    for suf in VISOES:
        logging.info(
            "kWp total%s: %.1f MW | local Res+Rural: %.1f MW",
            suf or " (corrigida)",
            tabela[f"kwp_total{suf}"].sum() / 1000,
            tabela[f"kwp_local_res_rural{suf}"].sum() / 1000,
        )

    config.PASTA_INTERIM_POTENCIAL.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(config.ARQUIVO_MMGD_MUNICIPAL, index=False)
    logging.info("Gravado: %s", config.ARQUIVO_MMGD_MUNICIPAL)
    return tabela


if __name__ == "__main__":
    construir_mmgd_municipal()
