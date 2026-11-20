"""
PROJETO: SolarGap Brasil
ARQUIVO: potencial/mmgd_municipal.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 19/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Agrega a MMGD solar por município (código IBGE de 7 dígitos), com
    detalhamento por classe de consumo e por modalidade.

LEITURA DA BASE (mesma regra da Silver do projeto):
    - ZIP bruto da ANEEL, sep=";", em chunks;
    - usecols = esquema.COLUNAS_ANEEL (sem NumCPFCNPJ e NomTitularEmpreendimento,
      LGPD) + as colunas de modalidade, que a Silver não carrega;
    - limpeza, correções e exclusões feitas por construir_silver.tratar_chunk
      (ano 1900, anteriores a 2012, potência <= 0, código de 6 dígitos, UF
      ausente, fonte imputada). Reusar a função — em vez de copiar a regra —
      garante que o total bata com a Silver.
    - filtro fonte = "Radiação solar" (esquema.FONTE_SOLAR).
    Por que não ler a Silver: ela não tem a modalidade, e reconstruí-la está
    fora do escopo. tratar_chunk preserva o índice do chunk, então a
    modalidade é recolocada por índice depois do tratamento.

COLUNAS DA BASE USADAS:
    CodMunicipioIbge             código IBGE do município (7 dígitos; os de 6
                                 são corrigidos por tratar_chunk)
    MdaPotenciaInstaladaKW       potência instalada em kW (decimal com vírgula).
                                 Para centrais fotovoltaicas a ANEEL registra a
                                 menor entre a potência dos módulos e a dos
                                 inversores; tratamos como kWp. Se o inversor
                                 limita a potência, y fica levemente subestimado
                                 (estimativa conservadora).
    DscClasseConsumo             classe de consumo
    DscModalidadeHabilitado      modalidade (própria UC, autoconsumo remoto,
                                 compartilhada, condomínio = múltiplas UCs)

SAÍDA:
    data/interim/potencial/mmgd_municipal.parquet — um registro por município
    com MMGD solar: cod_ibge, uf, kwp_total, n_unidades, kwp_local_res_rural,
    n_local_res_rural, kwp_classe_<classe>..., kwp_mod_<modalidade>...

OBS. DE USO:
    python -m src.potencial.mmgd_municipal      (~2 min: lê a base inteira)
"""

from __future__ import annotations

import logging
import re
import unicodedata
import zipfile
from collections import Counter

import pandas as pd

from src.data_acquisition.coletor_base import configurar_logging
from src.potencial import config
from src.preparacao import esquema
from src.preparacao.construir_silver import (
    ARQUIVO_IBGE_MUNICIPIO,
    ARQUIVO_ZIP,
    SEPARADOR,
    TAMANHO_CHUNK,
    ler_ibge_flat,
    tratar_chunk,
)
from src.preparacao.gerar_amostra import localizar_csv_no_zip

COLUNAS_MODALIDADE = ["DscModalidadeHabilitado"]
CHAVES = ["cod_ibge", "uf", "classe_consumo", "modalidade"]
SEM_INFORMACAO = "nao_informada"


def normalizar_rotulo(texto: str | None) -> str:
    """'Poder Público' -> 'poder_publico'; nulo -> 'nao_informada'."""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
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
    """Soma kW e conta unidades por município x UF x classe x modalidade.

    Entrada: um registro por empreendimento, com cod_municipio, sigla_uf,
    classe_consumo, modalidade (texto original) e potencia_kw.
    """
    df = pd.DataFrame(
        {
            "cod_ibge": registros["cod_municipio"].astype("Int64").astype(str),
            "uf": registros["sigla_uf"],
            "classe_consumo": registros["classe_consumo"].map(normalizar_rotulo),
            "modalidade": registros["modalidade"].map(rotulo_modalidade),
            "potencia_kw": registros["potencia_kw"].astype("float64"),
        }
    )
    return df.groupby(CHAVES, as_index=False, dropna=False).agg(
        kwp=("potencia_kw", "sum"), n=("potencia_kw", "size")
    )


def eh_local_res_rural(classe: pd.Series, modalidade: pd.Series) -> pd.Series:
    """Máscara da métrica principal: Residencial/Rural com geração na própria UC."""
    classes = {normalizar_rotulo(c) for c in config.CLASSES_PRINCIPAIS}
    return classe.isin(classes) & (
        modalidade == rotulo_modalidade(config.MODALIDADE_PRINCIPAL)
    )


def consolidar(resumo: pd.DataFrame) -> pd.DataFrame:
    """Do resumo longo para uma linha por município (colunas largas)."""
    resumo = resumo.groupby(CHAVES, as_index=False, dropna=False)[["kwp", "n"]].sum()

    base = resumo.groupby(["cod_ibge", "uf"], as_index=False).agg(
        kwp_total=("kwp", "sum"), n_unidades=("n", "sum")
    )

    local = resumo[eh_local_res_rural(resumo["classe_consumo"], resumo["modalidade"])]
    local = local.groupby("cod_ibge").agg(
        kwp_local_res_rural=("kwp", "sum"), n_local_res_rural=("n", "sum")
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
    resultado["n_unidades"] = resultado["n_unidades"].astype("int64")
    resultado["n_local_res_rural"] = resultado["n_local_res_rural"].astype("int64")
    colunas_fixas = [
        "cod_ibge",
        "uf",
        "kwp_total",
        "n_unidades",
        "kwp_local_res_rural",
        "n_local_res_rural",
    ]
    detalhe = sorted(c for c in resultado.columns if c not in colunas_fixas)
    return (
        resultado[colunas_fixas + detalhe]
        .sort_values("cod_ibge")
        .reset_index(drop=True)
    )


# ═══════════════════ Leitura da base ═══════════════════


def ler_resumo_aneel() -> tuple[pd.DataFrame, Counter]:
    """Percorre o ZIP em chunks e devolve o resumo longo + contagens."""
    municipio = ler_ibge_flat(ARQUIVO_IBGE_MUNICIPIO, "Município")
    municipio_7_digitos = {int(c) // 10: int(c) for c in municipio["codigo"]}

    contagem: Counter = Counter()
    partes = []
    nome_csv = localizar_csv_no_zip(ARQUIVO_ZIP)
    with (
        zipfile.ZipFile(ARQUIVO_ZIP) as arquivo_zip,
        arquivo_zip.open(nome_csv) as fluxo,
    ):
        leitor = pd.read_csv(
            fluxo,
            sep=SEPARADOR,
            encoding="utf-8",
            dtype=str,
            usecols=esquema.COLUNAS_ANEEL + COLUNAS_MODALIDADE,
            chunksize=TAMANHO_CHUNK,
        )
        for numero, chunk in enumerate(leitor, start=1):
            tratado = tratar_chunk(chunk, contagem, municipio_7_digitos)
            tratado = tratado.join(
                chunk["DscModalidadeHabilitado"].str.strip().rename("modalidade")
            )
            solar = tratado[tratado["fonte_geracao"] == esquema.FONTE_SOLAR]
            contagem["solar"] += len(solar)
            contagem["solar_sem_municipio"] += int(solar["cod_municipio"].isna().sum())
            partes.append(resumir_registros(solar[solar["cod_municipio"].notna()]))
            logging.info("  chunk %d — %d registros lidos", numero, contagem["lidos"])

    return pd.concat(partes, ignore_index=True), contagem


def construir_mmgd_municipal() -> pd.DataFrame:
    configurar_logging("POTENCIAL_MMGD", config.PASTA_LOGS)
    logging.info("Lendo base ANEEL: %s", ARQUIVO_ZIP.name)
    resumo, contagem = ler_resumo_aneel()
    tabela = consolidar(resumo)

    logging.info(
        "Lidos %d | mantidos %d | solares %d | solares sem município %d",
        contagem["lidos"],
        contagem["mantidos"],
        contagem["solar"],
        contagem["solar_sem_municipio"],
    )
    logging.info(
        "%d municípios com MMGD solar | %.1f MW | %d unidades",
        len(tabela),
        tabela["kwp_total"].sum() / 1000,
        tabela["n_unidades"].sum(),
    )

    config.PASTA_INTERIM_POTENCIAL.mkdir(parents=True, exist_ok=True)
    tabela.to_parquet(config.ARQUIVO_MMGD_MUNICIPAL, index=False)
    logging.info("Gravado: %s", config.ARQUIVO_MMGD_MUNICIPAL)
    return tabela


if __name__ == "__main__":
    construir_mmgd_municipal()
