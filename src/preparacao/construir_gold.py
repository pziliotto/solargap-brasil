"""
PROJETO: SolarGap Brasil
ARQUIVO: construir_gold.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/09/2026
ATUALIZAÇÃO: 21/10/2026 — TP3: junção opcional do ICMS removida (dimensão própria)
             20/11/2026 — TP4.5: potência corrigida (registros de 75 kW
             suspeitos) e limite conservador como medidas da Gold

DESCRIÇÃO:
    Constrói a camada Gold (data/processed) a partir da Silver (data/interim).
    É a camada VERSIONADA que alimenta o dashboard.

TABELAS:
    gold_mmgd_agregado.csv
        Grão: UF x ano x classe de consumo x fonte_imputada.
        Medidas: potência oficial (potencia_kw), potência corrigida
        (potencia_corrigida_kw, com os 75 kW suspeitos imputados), potência
        conservadora (potencia_conservadora_kw, só residenciais imputados),
        quantidade de empreendimentos e de registros com potência suspeita.
        Fica no menor nível que o painel precisa: filtros de período, classe
        e visão (corrigida ou critério ANEEL) são aplicados no app, que soma
        depois de filtrar. Uma tabela já totalizada travaria esses filtros.

    gold_uf.csv
        Grão: UF. Dimensão (nome, região, população) + indicadores do
        período completo na VISÃO CORRIGIDA (padrão do painel: com imputados
        e potência corrigida): potência (MW), watts por habitante,
        empreendimentos por 100 mil habitantes, % de registros imputados e %
        com potência suspeita. Para comparação: potencia_mw_aneel (critério do
        painel oficial: sem imputados, potência oficial) e
        potencia_mw_conservadora (limite conservador).

DECISÕES:
    - Apenas fonte solar (esquema.FONTE_SOLAR), incluindo registros com
      fonte imputada na Silver. A coluna fonte_imputada segue para a Gold
      para que o painel possa excluí-los.
    - Watts por habitante como métrica per capita principal: ordem de
      grandeza legível (centenas) e unidade usual no setor.
    - Empreendimentos por 100 mil hab. complementa a potência: potência mede
      volume investido, contagem mede difusão.
    - TP3: a adesão ao Convênio ICMS 16/15 NÃO é juntada aqui. Virou uma tabela
      Gold própria (gold_icms_uf.csv, gerada por icms_confaz.py), unida por
      sigla_uf sob demanda no painel e na API. Assim, atualizar a política não
      exige reprocessar 4,6 milhões de registros — nem ter a base da ANEEL.

OBS. DE USO:
    Rodar como módulo a partir da raiz, depois do construir_silver:
        python -m src.preparacao.construir_gold
"""

from __future__ import annotations

import logging
import sys

import pandas as pd

from src.data_acquisition.coletor_base import configurar_logging, obter_project_root
from src.preparacao import esquema

PROJECT_ROOT = obter_project_root(__file__)
PASTA_INTERIM = PROJECT_ROOT / "data" / "interim"
PASTA_PROCESSED = PROJECT_ROOT / "data" / "processed"
PASTA_LOGS = PROJECT_ROOT / "logs"

SILVER_MMGD = PASTA_INTERIM / "mmgd_silver.parquet"
SILVER_POP_UF = PASTA_INTERIM / "populacao_uf_silver.csv"

SAIDA_AGREGADO = PASTA_PROCESSED / "gold_mmgd_agregado.csv"
SAIDA_UF = PASTA_PROCESSED / "gold_uf.csv"

SEPARADOR = ";"
CHAVES_AGREGADO = ["sigla_uf", "ano", "classe_consumo", "fonte_imputada"]
COLUNAS_POTENCIA = ["potencia_kw", "potencia_corrigida_kw", "potencia_conservadora_kw"]
COLUNAS_SILVER = CHAVES_AGREGADO + COLUNAS_POTENCIA + ["flag_potencia_suspeita"]


def formatar(numero: float, casas: int = 0) -> str:
    """Formata números no padrão brasileiro: 4672363.5 -> 4.672.363,5."""
    texto = f"{numero:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def abortar(mensagem: str) -> None:
    logging.error(mensagem)
    sys.exit(1)


# ═══════════════════ Carga ═══════════════════


def carregar_solar() -> pd.DataFrame:
    """Lê da Silver só as colunas e linhas necessárias (filtro no Parquet)."""
    if not SILVER_MMGD.exists():
        abortar(f"Silver não encontrada: {SILVER_MMGD}. Rode antes o construir_silver.")

    solar = pd.read_parquet(
        SILVER_MMGD,
        columns=COLUNAS_SILVER,
        filters=[("fonte_geracao", "==", esquema.FONTE_SOLAR)],
    )

    if solar.empty:
        abortar(f"Nenhum registro com fonte '{esquema.FONTE_SOLAR}' na Silver.")

    solar["classe_consumo"] = solar["classe_consumo"].fillna("Não informada")
    logging.info("Registros solares lidos da Silver: %s", formatar(len(solar)))
    return solar


# ═══════════════════ Tabela agregada ═══════════════════


def construir_agregado(solar: pd.DataFrame) -> pd.DataFrame:
    agregado = solar.groupby(CHAVES_AGREGADO, as_index=False).agg(
        potencia_kw=("potencia_kw", "sum"),
        potencia_corrigida_kw=("potencia_corrigida_kw", "sum"),
        potencia_conservadora_kw=("potencia_conservadora_kw", "sum"),
        qtd_empreendimentos=("potencia_kw", "size"),
        qtd_potencia_suspeita=("flag_potencia_suspeita", "sum"),
    )
    agregado[COLUNAS_POTENCIA] = agregado[COLUNAS_POTENCIA].round(3)
    agregado["qtd_potencia_suspeita"] = agregado["qtd_potencia_suspeita"].astype(int)
    agregado["ano_parcial"] = agregado["ano"] == esquema.ANO_PARCIAL

    # Conferência: nenhum registro pode se perder no agrupamento.
    if agregado["qtd_empreendimentos"].sum() != len(solar):
        abortar("Soma de empreendimentos no agregado difere do total da Silver.")

    logging.info("Agregado: %s linhas", formatar(len(agregado)))
    return agregado.sort_values(CHAVES_AGREGADO).reset_index(drop=True)


# ═══════════════════ Tabela por UF ═══════════════════


def montar_dimensao_uf() -> pd.DataFrame:
    """Cadastro das UFs (esquema) + população (IBGE), com junção validada."""
    dimensao = pd.DataFrame(
        [
            {
                "sigla_uf": sigla,
                "cod_uf": cod,
                "nome_uf": nome,
                "regiao": esquema.REGIAO_POR_UF[sigla],
            }
            for sigla, (cod, nome) in esquema.UFS.items()
        ]
    )

    populacao = pd.read_csv(SILVER_POP_UF, sep=SEPARADOR)
    dimensao = dimensao.merge(
        populacao[["cod_uf", "populacao"]],
        on="cod_uf",
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    sem_par = dimensao[dimensao["_merge"] != "both"]
    if not sem_par.empty:
        abortar(f"UFs sem população do IBGE: {sem_par['sigla_uf'].tolist()}")

    return dimensao.drop(columns="_merge")


def construir_uf(agregado: pd.DataFrame) -> pd.DataFrame:
    dimensao = montar_dimensao_uf()

    # Visão corrigida (padrão): todos os registros, potência corrigida.
    totais = agregado.groupby("sigla_uf", as_index=False).agg(
        potencia_kw=("potencia_corrigida_kw", "sum"),
        potencia_conservadora_kw=("potencia_conservadora_kw", "sum"),
        qtd_empreendimentos=("qtd_empreendimentos", "sum"),
        qtd_potencia_suspeita=("qtd_potencia_suspeita", "sum"),
    )
    # Critério ANEEL: sem os registros imputados, potência oficial.
    aneel = (
        agregado[~agregado["fonte_imputada"]]
        .groupby("sigla_uf")["potencia_kw"]
        .sum()
        .rename("potencia_kw_aneel")
    )
    imputados = (
        agregado[agregado["fonte_imputada"]]
        .groupby("sigla_uf")["qtd_empreendimentos"]
        .sum()
        .rename("qtd_imputados")
    )

    uf = dimensao.merge(totais, on="sigla_uf", how="left", validate="one_to_one")
    uf = uf.merge(imputados, on="sigla_uf", how="left")
    uf = uf.merge(aneel, on="sigla_uf", how="left")
    uf["qtd_imputados"] = uf["qtd_imputados"].fillna(0).astype(int)
    uf["potencia_kw_aneel"] = uf["potencia_kw_aneel"].fillna(0)

    sem_dado = uf[uf["qtd_empreendimentos"].isna()]
    if not sem_dado.empty:
        abortar(f"UFs sem nenhum registro solar: {sem_dado['sigla_uf'].tolist()}")

    uf["qtd_empreendimentos"] = uf["qtd_empreendimentos"].astype(int)
    uf["potencia_mw"] = (uf["potencia_kw"] / 1_000).round(3)
    uf["watts_por_habitante"] = (uf["potencia_kw"] * 1_000 / uf["populacao"]).round(1)
    uf["empreendimentos_por_100k_hab"] = (
        uf["qtd_empreendimentos"] / uf["populacao"] * 100_000
    ).round(1)
    uf["pct_imputados"] = (uf["qtd_imputados"] / uf["qtd_empreendimentos"] * 100).round(
        2
    )
    uf["pct_potencia_suspeita"] = (
        uf["qtd_potencia_suspeita"] / uf["qtd_empreendimentos"] * 100
    ).round(2)
    uf["potencia_mw_aneel"] = (uf["potencia_kw_aneel"] / 1_000).round(3)
    uf["potencia_mw_conservadora"] = (uf["potencia_conservadora_kw"] / 1_000).round(3)

    uf = uf.drop(
        columns=[
            "potencia_kw",
            "potencia_kw_aneel",
            "potencia_conservadora_kw",
            "qtd_imputados",
            "qtd_potencia_suspeita",
        ]
    )

    if len(uf) != esquema.TOTAL_UFS:
        abortar(f"Tabela por UF com {len(uf)} linhas; esperado {esquema.TOTAL_UFS}.")

    return uf.sort_values("watts_por_habitante", ascending=False).reset_index(drop=True)


# ═══════════════════ Resumo ═══════════════════


def registrar_resumo(uf: pd.DataFrame) -> None:
    logging.info("--- Resumo da Gold ---")
    logging.info(
        "Potência solar total : %s MW (corrigida) | %s MW (critério ANEEL) | "
        "%s MW (conservadora)",
        formatar(uf["potencia_mw"].sum(), 1),
        formatar(uf["potencia_mw_aneel"].sum(), 1),
        formatar(uf["potencia_mw_conservadora"].sum(), 1),
    )
    logging.info("Empreendimentos .....: %s", formatar(uf["qtd_empreendimentos"].sum()))
    logging.info("População ...........: %s", formatar(uf["populacao"].sum()))

    colunas = [
        "sigla_uf",
        "watts_por_habitante",
        "empreendimentos_por_100k_hab",
        "potencia_mw",
    ]

    logging.info("--- 5 maiores em watts por habitante ---")
    for _, linha in uf.head(5)[colunas].iterrows():
        logging.info(
            "  %-3s %7s W/hab | %7s emp/100k | %10s MW",
            linha["sigla_uf"],
            formatar(linha["watts_por_habitante"], 1),
            formatar(linha["empreendimentos_por_100k_hab"], 1),
            formatar(linha["potencia_mw"], 1),
        )

    logging.info("--- 5 menores em watts por habitante ---")
    for _, linha in uf.tail(5)[colunas].iterrows():
        logging.info(
            "  %-3s %7s W/hab | %7s emp/100k | %10s MW",
            linha["sigla_uf"],
            formatar(linha["watts_por_habitante"], 1),
            formatar(linha["empreendimentos_por_100k_hab"], 1),
            formatar(linha["potencia_mw"], 1),
        )

    com_imputados = uf[uf["pct_imputados"] >= 1]
    if not com_imputados.empty:
        logging.info("--- UFs com 1% ou mais de registros imputados ---")
        for _, linha in com_imputados.iterrows():
            logging.info(
                "  %-3s %s%%", linha["sigla_uf"], formatar(linha["pct_imputados"], 2)
            )


# ═══════════════════ Execução ═══════════════════


def salvar(df: pd.DataFrame, destino) -> None:
    df.to_csv(destino, index=False, sep=SEPARADOR, encoding="utf-8")
    logging.info("Salvo: %s (%.1f KB)", destino, destino.stat().st_size / 1024)


def construir_gold() -> None:
    caminho_log = configurar_logging("GOLD", PASTA_LOGS)
    logging.info("=" * 70)
    logging.info("Construção da camada Gold")
    logging.info("Raiz do projeto: %s", PROJECT_ROOT)

    PASTA_PROCESSED.mkdir(parents=True, exist_ok=True)

    solar = carregar_solar()
    agregado = construir_agregado(solar)
    uf = construir_uf(agregado)

    salvar(agregado, SAIDA_AGREGADO)
    salvar(uf, SAIDA_UF)
    registrar_resumo(uf)

    logging.info("Log da sessão: %s", caminho_log)
    logging.info("Concluído.")
    logging.info("=" * 70)


if __name__ == "__main__":
    construir_gold()
