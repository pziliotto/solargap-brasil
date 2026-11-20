"""
PROJETO: SolarGap Brasil
ARQUIVO: potencial/irradiacao.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 19/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Camada Silver da irradiação municipal: cruza os pontos dos municípios com o
    cache Bronze da NASA POWER e calcula a irradiação média de ANOS_BASE.

SAÍDA:
    data/interim/potencial/irradiacao_municipal.parquet
        cod_ibge, uf, irradiacao_kwh_m2_dia, n_meses_validos, celula_power

DECISÕES:
    - Média dos 36 meses PONDERADA pelos dias de cada mês (fevereiro de 2024
      com 29 dias). Média simples dos meses daria a fevereiro o mesmo peso de
      janeiro e enviesaria a média anual para baixo ou para cima conforme a
      estação. Multiplicada por 365, a média ponderada reproduz a energia anual.
    - A média anual que o POWER já entrega (mês "13") é ignorada: recalculá-la
      deixa a regra explícita e permite contar os meses válidos.
    - -999 (valor de preenchimento) e valores ausentes viram NaN e ficam fora da
      média; n_meses_validos registra quantos meses entraram.

OBS. DE USO:
    python -m src.potencial.irradiacao
    (requer malha_municipal e coletor_nasa_power já executados)
"""

from __future__ import annotations

import calendar
import logging

import numpy as np
import pandas as pd

from src.data_acquisition import coletor_nasa_power as power
from src.data_acquisition.coletor_base import configurar_logging
from src.potencial import config
from src.preparacao.esquema import REGIAO_POR_UF

COLUNAS_SILVER = [
    "cod_ibge",
    "uf",
    "irradiacao_kwh_m2_dia",
    "n_meses_validos",
    "celula_power",
]


# ═══════════════════ Série mensal ═══════════════════


def extrair_serie_mensal(
    payload: dict, anos: tuple[int, ...] = config.ANOS_BASE
) -> pd.Series:
    """Série mensal (índice (ano, mês)) do parâmetro, com -999 como NaN.

    Usa o fill_value declarado no cabeçalho da resposta quando presente; senão,
    o -999 documentado. O mês 13 (média anual) é descartado.
    """
    serie_bruta = payload["properties"]["parameter"][power.PARAMETRO]
    preenchimento = payload.get("header", {}).get(
        "fill_value", power.VALOR_PREENCHIMENTO
    )
    valores = {}
    for ano in anos:
        for mes in range(1, 13):
            valor = serie_bruta.get(f"{ano}{mes:02d}")
            if valor is None or np.isclose(float(valor), float(preenchimento)):
                valores[(ano, mes)] = np.nan
            else:
                valores[(ano, mes)] = float(valor)
    indice = pd.MultiIndex.from_tuples(valores.keys(), names=["ano", "mes"])
    return pd.Series(list(valores.values()), index=indice, dtype="float64")


def media_ponderada_por_dias(serie_mensal: pd.Series) -> tuple[float, int]:
    """Média dos meses válidos ponderada pelo número de dias de cada mês.

    Devolve (média, n_meses_validos); a média é NaN se nenhum mês for válido.
    """
    dias = np.array(
        [calendar.monthrange(ano, mes)[1] for ano, mes in serie_mensal.index],
        dtype="float64",
    )
    valores = serie_mensal.to_numpy(dtype="float64")
    validos = ~np.isnan(valores)
    n_validos = int(validos.sum())
    if n_validos == 0:
        return float("nan"), 0
    media = float(np.average(valores[validos], weights=dias[validos]))
    return media, n_validos


def resumir_celula(payload: dict, anos: tuple[int, ...] = config.ANOS_BASE) -> dict:
    media, n_validos = media_ponderada_por_dias(extrair_serie_mensal(payload, anos))
    return {"irradiacao_kwh_m2_dia": media, "n_meses_validos": n_validos}


# ═══════════════════ Silver ═══════════════════


def montar_silver(
    pontos: pd.DataFrame, payloads_por_celula: dict[str, dict]
) -> pd.DataFrame:
    """Combina pontos e respostas do POWER na tabela Silver (função pura).

    Célula sem payload resulta em irradiação NaN — capturada pela validação.
    """
    pontos = power.atribuir_celulas(pontos)
    resumo = pd.DataFrame(
        [
            {"celula_power": celula, **resumir_celula(payload)}
            for celula, payload in payloads_por_celula.items()
        ],
        columns=["celula_power", "irradiacao_kwh_m2_dia", "n_meses_validos"],
    )
    silver = pontos.merge(resumo, on="celula_power", how="left")
    silver["n_meses_validos"] = silver["n_meses_validos"].fillna(0).astype("int64")
    return silver[COLUNAS_SILVER].sort_values("cod_ibge").reset_index(drop=True)


def carregar_payloads(celulas: pd.Series) -> dict[str, dict]:
    """Lê do cache Bronze as células pedidas (ausentes ficam de fora)."""
    payloads = {}
    for celula in celulas.unique():
        payload = power.ler_cache(power.caminho_cache(celula))
        if payload is None:
            logging.error("Célula %s ausente ou inválida no cache", celula)
        else:
            payloads[celula] = payload
    return payloads


# ═══════════════════ Validação ═══════════════════


def validar_silver(silver: pd.DataFrame) -> list[str]:
    """Lista os problemas encontrados (vazia = Silver válida)."""
    problemas = []
    sem_valor = silver["irradiacao_kwh_m2_dia"].isna()
    if sem_valor.any():
        problemas.append(f"{sem_valor.sum()} município(s) sem irradiação")

    minimo, maximo = config.FAIXA_PLAUSIVEL_KWH_M2_DIA
    fora = silver["irradiacao_kwh_m2_dia"].notna() & ~silver[
        "irradiacao_kwh_m2_dia"
    ].between(minimo, maximo)
    if fora.any():
        problemas.append(
            f"{fora.sum()} município(s) fora da faixa {minimo}–{maximo} kWh/m²/dia"
        )

    if len(silver) != config.TOTAL_MUNICIPIOS:
        problemas.append(
            f"{len(silver)} municípios (esperado {config.TOTAL_MUNICIPIOS})"
        )

    regiao = silver.groupby(silver["uf"].map(REGIAO_POR_UF))[
        "irradiacao_kwh_m2_dia"
    ].mean()
    for candidata in ("Nordeste", "Centro-Oeste"):
        if not regiao.get(candidata, np.nan) > regiao.get("Sul", np.nan):
            problemas.append(f"Sanidade: {candidata} não ficou acima do Sul")
    return problemas


def relatorio(silver: pd.DataFrame, pontos: pd.DataFrame) -> str:
    """Texto com média por UF e por região e os extremos municipais."""
    linhas = []
    por_uf = (
        silver.groupby("uf")["irradiacao_kwh_m2_dia"]
        .agg(["mean", "min", "max", "count"])
        .sort_values("mean", ascending=False)
    )
    linhas.append("Irradiação média 2023–2025 por UF (kWh/m²/dia):")
    linhas.append(por_uf.round(3).to_string())

    regiao = (
        silver.groupby(silver["uf"].map(REGIAO_POR_UF))["irradiacao_kwh_m2_dia"]
        .mean()
        .sort_values(ascending=False)
    )
    linhas.append("\nMédia por região (média simples dos municípios):")
    linhas.append(regiao.round(3).to_string())

    com_nome = silver.merge(pontos[["cod_ibge", "nome"]], on="cod_ibge")
    colunas = ["cod_ibge", "nome", "uf", "irradiacao_kwh_m2_dia", "celula_power"]
    linhas.append("\n5 maiores:")
    linhas.append(
        com_nome.nlargest(5, "irradiacao_kwh_m2_dia")[colunas].to_string(index=False)
    )
    linhas.append("\n5 menores:")
    linhas.append(
        com_nome.nsmallest(5, "irradiacao_kwh_m2_dia")[colunas].to_string(index=False)
    )
    return "\n".join(linhas)


def construir_irradiacao() -> pd.DataFrame:
    """Monta, valida e grava a Silver. Falha alto se a validação reprovar."""
    configurar_logging("POTENCIAL_IRRADIACAO", config.PASTA_LOGS)
    pontos = pd.read_parquet(config.ARQUIVO_PONTOS)
    celulas = power.atribuir_celulas(pontos)["celula_power"]
    silver = montar_silver(pontos, carregar_payloads(celulas))

    texto = relatorio(silver, pontos)
    logging.info("\n%s", texto)

    problemas = validar_silver(silver)
    if problemas:
        for problema in problemas:
            logging.error("Validação: %s", problema)
        raise ValueError("Silver de irradiação reprovada: " + "; ".join(problemas))

    config.PASTA_INTERIM_POTENCIAL.mkdir(parents=True, exist_ok=True)
    silver.to_parquet(config.ARQUIVO_IRRADIACAO, index=False)
    logging.info(
        "Validação OK — %d municípios gravados em %s",
        len(silver), config.ARQUIVO_IRRADIACAO,
    )
    return silver


if __name__ == "__main__":
    construir_irradiacao()
