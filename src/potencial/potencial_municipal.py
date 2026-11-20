"""
PROJETO: SolarGap Brasil
ARQUIVO: potencial/potencial_municipal.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 19/11/2026
ATUALIZAÇÃO: 20/11/2026 — visão corrigida (75 kW suspeitos imputados) como
             padrão; critério ANEEL e limite conservador em colunas próprias

DESCRIÇÃO:
    Camada Gold do potencial solar municipal: potencial técnico em telhados (x),
    geração estimada da MMGD instalada (y) e o gap entre os dois, por município
    e por UF.

FÓRMULAS (H = irradiação média 2023–2025, kWh/m²/dia; premissas em config.py):
    kwp_potencial   = domicilios x AREA_UTIL_TELHADO_M2 x EFICIENCIA_PAINEL
                      (1 m² com 20% de eficiência ≈ 0,2 kWp, pois a STC é 1 kW/m²)
    x_mwh_ano       = kwp_potencial       x H x PR x 365 / 1000
    y_mwh_ano       = kwp_local_res_rural x H x PR x 365 / 1000
    y_total_mwh_ano = kwp_total           x H x PR x 365 / 1000
    gap_mwh_ano     = x - y
    taxa_realizacao = y / x
    x_mwh_ano_area_<A>m2: x com a área útil A de AREAS_SENSIBILIDADE_M2.

    kWp x H (kWh/m²/dia) dá kWh/dia: H em kWh/m²/dia equivale a "horas de sol
    pleno" a 1 kW/m², e 1 kWp produz 1 kW nessa irradiância.

TAXA DE REALIZAÇÃO E IRRADIAÇÃO:
    Em taxa_realizacao a irradiação H se CANCELA: x e y usam o mesmo H e o mesmo
    PR, então y/x = kwp_local_res_rural / kwp_potencial — kWp instalado sobre
    kWp potencial. A taxa mede adoção, não recurso solar. H segue importante:
    determina o gap em MWh (quanto de energia deixa de ser gerado) e entra como
    variável explicativa na Tarefa 4.

VISÕES DE y (mesmo padrão do painel):
    y_mwh_ano, taxa_realizacao, flag_taxa_acima_1 — visão corrigida (padrão):
        potência dos registros de 75 kW suspeitos imputada na Silver;
    *_aneel — critério ANEEL: potência oficial, sem registros de fonte imputada;
    *_conservador — limite conservador: só os residenciais de 75 kW corrigidos.

RECORTE DE y (métrica principal):
    Só classes Residencial + Rural com modalidade "Geração na própria UC"
    (config.CLASSES_PRINCIPAIS, config.MODALIDADE_PRINCIPAL). Autoconsumo remoto
    e geração compartilhada costumam ser usinas instaladas num município que
    abastecem consumidores de outros. y_total (todas as classes e modalidades) e
    o kWp por classe e por modalidade ficam em colunas separadas.

FLAG flag_taxa_acima_1:
    Municípios com y > x são marcados, não descartados. Indicam telhados maiores
    que a premissa de 15 m² (casas rurais, alto padrão), domicílios de uso
    ocasional (veraneio) fora do universo "ocupados" ou registros de UC
    classificados como residenciais/rurais mas instalados em solo. No critério
    ANEEL, o agrupamento do Oeste do Paraná com taxa > 1 era efeito dos
    registros de 75 kW suspeitos.

SAÍDAS:
    data/processed/potencial_municipal.parquet e .csv (sep=";")
    data/processed/potencial_uf.parquet

OBS. DE USO:
    python -m src.potencial.potencial_municipal
    (requer irradiacao, mmgd_municipal e ibge_domicilios já executados)
"""

from __future__ import annotations

import logging

import pandas as pd

from src.data_acquisition import ibge_domicilios
from src.data_acquisition.coletor_base import configurar_logging
from src.potencial import config, referencia_epe
from src.preparacao import esquema

DIAS_ANO = 365
SEPARADOR_CSV = ";"
ARQUIVO_GOLD_UF_PROJETO = config.PASTA_PROCESSED / "gold_uf.csv"
ARQUIVO_SILVER_MMGD = config.PROJECT_ROOT / "data" / "interim" / "mmgd_silver.parquet"


# Sufixo das colunas kWp da MMGD -> sufixo das colunas y e taxa
VISOES_Y = {"": "", "_aneel": "_aneel", "_conservadora": "_conservador"}


def coluna_sensibilidade(area_m2: float) -> str:
    return f"x_mwh_ano_area_{area_m2:g}m2"


# ═══════════════════ Fórmulas ═══════════════════


def kwp_potencial(domicilios, area_m2: float = config.AREA_UTIL_TELHADO_M2):
    """Potência de pico que caberia nos telhados (kWp)."""
    return domicilios * area_m2 * config.KWP_POR_M2


def energia_mwh_ano(kwp, irradiacao_kwh_m2_dia, pr: float = config.PR):
    """Energia anual (MWh) de uma potência kWp sob irradiação H."""
    return kwp * irradiacao_kwh_m2_dia * pr * DIAS_ANO / 1000


# ═══════════════════ Montagem da Gold ═══════════════════


def reatribuir_municipios_novos(
    mmgd: pd.DataFrame, mapa: dict[str, str] = config.MUNICIPIOS_POSTERIORES_2022
) -> pd.DataFrame:
    """Soma a MMGD de municípios posteriores a 2022 ao município de origem."""
    if not mmgd["cod_ibge"].isin(list(mapa)).any():
        return mmgd
    mmgd = mmgd.copy()
    for novo, origem in mapa.items():
        if (mmgd["cod_ibge"] == novo).any():
            logging.info(
                "MMGD de %s reatribuída a %s (município posterior a 2022)", novo, origem
            )
    mmgd["cod_ibge"] = mmgd["cod_ibge"].replace(mapa)
    numericas = [c for c in mmgd.columns if c not in ("cod_ibge", "uf")]
    uf = mmgd.groupby("cod_ibge")["uf"].first()
    somado = mmgd.groupby("cod_ibge")[numericas].sum()
    return somado.join(uf).reset_index()[mmgd.columns]


def montar_gold(
    pontos: pd.DataFrame,
    irradiacao: pd.DataFrame,
    domicilios: pd.DataFrame,
    mmgd: pd.DataFrame,
) -> pd.DataFrame:
    """Junta as quatro entradas e calcula x, y e gap (função pura).

    A base é a malha municipal (5.570). Município sem MMGD recebe kWp zero;
    sem irradiação ou domicílios, a junção falha alto (validate + checagem).
    """
    base = pontos[["cod_ibge", "nome", "uf"]].merge(
        irradiacao[["cod_ibge", "irradiacao_kwh_m2_dia"]],
        on="cod_ibge",
        how="left",
        validate="one_to_one",
    )
    base = base.merge(
        domicilios[["cod_ibge", "domicilios"]],
        on="cod_ibge",
        how="left",
        validate="one_to_one",
    )
    faltando = base[["irradiacao_kwh_m2_dia", "domicilios"]].isna().any(axis=1)
    if faltando.any():
        raise ValueError(
            f"{faltando.sum()} município(s) sem irradiação ou domicílios: "
            f"{base.loc[faltando, 'cod_ibge'].head().tolist()}"
        )

    mmgd = reatribuir_municipios_novos(mmgd)
    sem_malha = set(mmgd["cod_ibge"]) - set(base["cod_ibge"])
    if sem_malha:
        raise ValueError(f"Municípios da MMGD fora da malha: {sorted(sem_malha)[:5]}")

    colunas_mmgd = [c for c in mmgd.columns if c not in ("uf",)]
    gold = base.merge(
        mmgd[colunas_mmgd], on="cod_ibge", how="left", validate="one_to_one"
    )
    colunas_kwp = [c for c in colunas_mmgd if c != "cod_ibge"]
    gold[colunas_kwp] = gold[colunas_kwp].fillna(0)
    for coluna in ("n_unidades", "n_potencia_suspeita", "n_local_res_rural"):
        gold[coluna] = gold[coluna].astype("int64")

    gold["regiao"] = gold["uf"].map(esquema.REGIAO_POR_UF)
    h = gold["irradiacao_kwh_m2_dia"]

    gold["kwp_potencial"] = kwp_potencial(gold["domicilios"])
    gold["x_mwh_ano"] = energia_mwh_ano(gold["kwp_potencial"], h)
    # Visão corrigida (padrão) e, para comparação, critério ANEEL e conservadora
    for sufixo_kwp, sufixo_y in VISOES_Y.items():
        gold[f"y{sufixo_y}_mwh_ano"] = energia_mwh_ano(
            gold[f"kwp_local_res_rural{sufixo_kwp}"], h
        )
        gold[f"taxa_realizacao{sufixo_y}"] = (
            gold[f"y{sufixo_y}_mwh_ano"] / gold["x_mwh_ano"]
        )
    gold["y_total_mwh_ano"] = energia_mwh_ano(gold["kwp_total"], h)
    gold["y_total_aneel_mwh_ano"] = energia_mwh_ano(gold["kwp_total_aneel"], h)
    gold["gap_mwh_ano"] = gold["x_mwh_ano"] - gold["y_mwh_ano"]
    gold["flag_taxa_acima_1"] = gold["taxa_realizacao"] > 1
    gold["flag_taxa_acima_1_aneel"] = gold["taxa_realizacao_aneel"] > 1

    for area in config.AREAS_SENSIBILIDADE_M2:
        gold[coluna_sensibilidade(area)] = energia_mwh_ano(
            kwp_potencial(gold["domicilios"], area), h
        )

    principais = (
        [
            "cod_ibge",
            "nome",
            "uf",
            "regiao",
            "domicilios",
            "irradiacao_kwh_m2_dia",
            "kwp_potencial",
            "kwp_local_res_rural",
            "n_local_res_rural",
            "kwp_total",
            "n_unidades",
            "n_potencia_suspeita",
            "x_mwh_ano",
            "y_mwh_ano",
            "y_total_mwh_ano",
            "gap_mwh_ano",
            "taxa_realizacao",
            "flag_taxa_acima_1",
        ]
        + [coluna_sensibilidade(a) for a in config.AREAS_SENSIBILIDADE_M2]
        + [
            "kwp_local_res_rural_aneel",
            "kwp_total_aneel",
            "y_aneel_mwh_ano",
            "y_total_aneel_mwh_ano",
            "taxa_realizacao_aneel",
            "flag_taxa_acima_1_aneel",
            "kwp_local_res_rural_conservadora",
            "kwp_total_conservadora",
            "y_conservador_mwh_ano",
            "taxa_realizacao_conservador",
        ]
    )
    detalhe = sorted(
        c for c in gold.columns if c.startswith(("kwp_classe_", "kwp_mod_"))
    )
    return gold[principais + detalhe].sort_values("cod_ibge").reset_index(drop=True)


def agregar_uf(gold: pd.DataFrame) -> pd.DataFrame:
    """Somas por UF; taxa = Σy / Σx (não a média das taxas municipais)."""
    somar = [
        "domicilios",
        "kwp_potencial",
        "kwp_local_res_rural",
        "kwp_total",
        "n_unidades",
        "n_potencia_suspeita",
        "n_local_res_rural",
        "x_mwh_ano",
        "y_mwh_ano",
        "y_total_mwh_ano",
        "gap_mwh_ano",
        "kwp_local_res_rural_aneel",
        "kwp_total_aneel",
        "y_aneel_mwh_ano",
        "y_total_aneel_mwh_ano",
        "kwp_local_res_rural_conservadora",
        "y_conservador_mwh_ano",
    ] + [coluna_sensibilidade(a) for a in config.AREAS_SENSIBILIDADE_M2]
    uf = gold.groupby(["uf", "regiao"], as_index=False).agg(
        n_municipios=("cod_ibge", "size"),
        n_municipios_taxa_acima_1=("flag_taxa_acima_1", "sum"),
        n_municipios_taxa_acima_1_aneel=("flag_taxa_acima_1_aneel", "sum"),
        **{coluna: (coluna, "sum") for coluna in somar},
    )
    for sufixo in VISOES_Y.values():
        uf[f"taxa_realizacao{sufixo}"] = uf[f"y{sufixo}_mwh_ano"] / uf["x_mwh_ano"]
    uf["taxa_realizacao_total"] = uf["y_total_mwh_ano"] / uf["x_mwh_ano"]
    for coluna in ("n_municipios_taxa_acima_1", "n_municipios_taxa_acima_1_aneel"):
        uf[coluna] = uf[coluna].astype("int64")
    uf["x_epe_2014_gwh_ano"] = uf["uf"].map(referencia_epe.POTENCIAL_EPE_GWH_ANO)
    uf["razao_x_sobre_epe"] = (uf["x_mwh_ano"] / 1000) / uf["x_epe_2014_gwh_ano"]
    return uf.sort_values("gap_mwh_ano", ascending=False).reset_index(drop=True)


# ═══════════════════ Validação ═══════════════════


def total_reportado_kw(coluna_mw: str = "potencia_mw") -> float:
    """MMGD solar total da Gold do projeto (gold_uf.csv), em kW.

    potencia_mw = visão corrigida; potencia_mw_aneel = critério ANEEL.
    """
    uf = pd.read_csv(ARQUIVO_GOLD_UF_PROJETO, sep=SEPARADOR_CSV)
    return float(uf[coluna_mw].sum() * 1000)


def total_silver_kw(visao: str = "corrigida") -> float:
    """MMGD solar total na Silver do projeto, em kW.

    corrigida: potencia_corrigida_kw de todos os registros; aneel: potência
    oficial sem os registros de fonte imputada.
    """
    silver = pd.read_parquet(
        ARQUIVO_SILVER_MMGD,
        columns=["potencia_kw", "potencia_corrigida_kw", "fonte_imputada"],
        filters=[("fonte_geracao", "==", esquema.FONTE_SOLAR)],
    )
    if visao == "aneel":
        return float(silver.loc[~silver["fonte_imputada"], "potencia_kw"].sum())
    return float(silver["potencia_corrigida_kw"].sum())


def diferenca_relativa(valor: float, referencia: float) -> float:
    return abs(valor - referencia) / referencia


def validar_gold(
    gold: pd.DataFrame,
    referencias_kw: dict[str, float],
    referencias_aneel_kw: dict[str, float] | None = None,
) -> list[str]:
    """Problemas que impedem gravar a Gold (lista vazia = OK).

    referencias_kw: {nome: total nacional em kW} da visão corrigida, comparado a
    kwp_total; referencias_aneel_kw: idem para o critério ANEEL, comparado a
    kwp_total_aneel. Cada total precisa ficar a menos de
    config.TOLERANCIA_TOTAL_KWP de CADA referência.
    """
    problemas = []
    if len(gold) != config.TOTAL_MUNICIPIOS:
        problemas.append(f"{len(gold)} municípios (esperado {config.TOTAL_MUNICIPIOS})")
    if gold[["x_mwh_ano", "y_mwh_ano", "taxa_realizacao"]].isna().any().any():
        problemas.append("valores ausentes em x, y ou taxa")
    if (gold["x_mwh_ano"] <= 0).any():
        problemas.append("x <= 0 em algum município")
    conferencias = [("kWp nacional", "kwp_total", referencias_kw)]
    if referencias_aneel_kw:
        conferencias.append(
            ("kWp nacional (critério ANEEL)", "kwp_total_aneel", referencias_aneel_kw)
        )
    for rotulo, coluna, referencias in conferencias:
        total = gold[coluna].sum()
        for nome, total_kw in referencias.items():
            diferenca = diferenca_relativa(total, total_kw)
            if diferenca >= config.TOLERANCIA_TOTAL_KWP:
                problemas.append(
                    f"{rotulo} difere {diferenca:.2%} de {nome} (limite "
                    f"{config.TOLERANCIA_TOTAL_KWP:.0%})"
                )
    return problemas


# ═══════════════════ Relatório ═══════════════════


def _fmt(valor: float, casas: int = 0) -> str:
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def relatorio(gold: pd.DataFrame, uf: pd.DataFrame) -> str:
    linhas = []
    colunas = [
        "cod_ibge",
        "nome",
        "uf",
        "domicilios",
        "x_mwh_ano",
        "y_mwh_ano",
        "gap_mwh_ano",
        "taxa_realizacao",
    ]
    pd.set_option("display.width", 200)

    linhas.append("Top 10 gaps absolutos (MWh/ano):")
    linhas.append(
        gold.nlargest(10, "gap_mwh_ano")[colunas].round(3).to_string(index=False)
    )

    grandes = gold[gold["domicilios"] > 5000]
    linhas.append(
        f"\nTop 10 taxas (municípios com > 5 mil domicílios: {len(grandes)}):"
    )
    linhas.append(
        grandes.nlargest(10, "taxa_realizacao")[colunas].round(3).to_string(index=False)
    )
    linhas.append("\nBottom 10 taxas (> 5 mil domicílios):")
    linhas.append(
        grandes.nsmallest(10, "taxa_realizacao")[colunas]
        .round(4)
        .to_string(index=False)
    )

    linhas.append("\nPor UF (GWh/ano):")
    tabela_uf = uf.assign(
        x_gwh=uf["x_mwh_ano"] / 1000,
        y_gwh=uf["y_mwh_ano"] / 1000,
        gap_gwh=uf["gap_mwh_ano"] / 1000,
    )[
        [
            "uf",
            "regiao",
            "x_gwh",
            "y_gwh",
            "gap_gwh",
            "taxa_realizacao",
            "taxa_realizacao_total",
            "x_epe_2014_gwh_ano",
            "razao_x_sobre_epe",
            "n_municipios_taxa_acima_1",
        ]
    ]
    linhas.append(tabela_uf.round(3).to_string(index=False))

    x, y = gold["x_mwh_ano"].sum(), gold["y_mwh_ano"].sum()
    linhas.append(
        f"\nBrasil: x = {_fmt(x / 1e6, 1)} TWh/ano | y = {_fmt(y / 1e6, 2)} TWh/ano | "
        f"y_total = {_fmt(gold['y_total_mwh_ano'].sum() / 1e6, 2)} TWh/ano | "
        f"taxa = {y / x:.2%} | EPE 2014 = {_fmt(referencia_epe.TOTAL_BRASIL_GWH_ANO / 1000, 1)} TWh/ano"
    )
    for rotulo, sufixo in (
        ("critério ANEEL", "_aneel"),
        ("conservador", "_conservador"),
    ):
        y_visao = gold[f"y{sufixo}_mwh_ano"].sum()
        acima_visao = int((gold[f"taxa_realizacao{sufixo}"] > 1).sum())
        linhas.append(
            f"  {rotulo}: y = {_fmt(y_visao / 1e6, 2)} TWh/ano | taxa = {y_visao / x:.2%} "
            f"| municípios com taxa > 1: {acima_visao}"
        )

    linhas.append("\nSensibilidade da área útil (Brasil):")
    for area in config.AREAS_SENSIBILIDADE_M2:
        x_area = gold[coluna_sensibilidade(area)].sum()
        linhas.append(
            f"  {area:>2} m²: x = {_fmt(x_area / 1e6, 1)} TWh/ano | taxa = {y / x_area:.2%}"
        )

    acima = gold[gold["flag_taxa_acima_1"]].sort_values(
        "taxa_realizacao", ascending=False
    )
    linhas.append(f"\nMunicípios com taxa > 1: {len(acima)}")
    if len(acima):
        linhas.append(acima[colunas].round(3).to_string(index=False))
    return "\n".join(linhas)


# ═══════════════════ Execução ═══════════════════


def construir_potencial() -> tuple[pd.DataFrame, pd.DataFrame]:
    configurar_logging("POTENCIAL_GOLD", config.PASTA_LOGS)
    pontos = pd.read_parquet(config.ARQUIVO_PONTOS)
    irradiacao = pd.read_parquet(config.ARQUIVO_IRRADIACAO)
    domicilios = ibge_domicilios.ler_domicilios()
    mmgd = pd.read_parquet(config.ARQUIVO_MMGD_MUNICIPAL)

    gold = montar_gold(pontos, irradiacao, domicilios, mmgd)
    uf = agregar_uf(gold)

    # Conferência do total nacional contra a Silver (isola erro de método) e
    # contra a Gold do projeto (gold_uf.csv, o total publicado). Desde a
    # unificação na base ANEEL 10/2026 as três leem a mesma base e precisam
    # bater (docs/potencial/atualizacao_base_10_2026.md).
    referencias = {
        "Silver (mmgd_silver.parquet)": total_silver_kw("corrigida"),
        "Gold do projeto (gold_uf.csv)": total_reportado_kw("potencia_mw"),
    }
    referencias_aneel = {
        "Silver (mmgd_silver.parquet)": total_silver_kw("aneel"),
        "Gold do projeto (gold_uf.csv)": total_reportado_kw("potencia_mw_aneel"),
    }
    for visao, coluna, refs in (
        ("corrigida", "kwp_total", referencias),
        ("critério ANEEL", "kwp_total_aneel", referencias_aneel),
    ):
        total = gold[coluna].sum()
        for nome, total_kw in refs.items():
            logging.info(
                "kWp nacional (%s) %s x %s %s (%.3f%%)",
                visao,
                _fmt(total),
                nome,
                _fmt(total_kw),
                100 * diferenca_relativa(total, total_kw),
            )

    logging.info("\n%s", relatorio(gold, uf))

    problemas = validar_gold(gold, referencias, referencias_aneel)
    if problemas:
        for problema in problemas:
            logging.error("Validação: %s", problema)
        raise ValueError("Gold de potencial reprovada: " + "; ".join(problemas))

    config.PASTA_PROCESSED.mkdir(parents=True, exist_ok=True)
    gold.to_parquet(config.ARQUIVO_GOLD_MUNICIPAL, index=False)
    gold.to_csv(
        config.ARQUIVO_GOLD_MUNICIPAL_CSV,
        sep=SEPARADOR_CSV,
        index=False,
        encoding="utf-8",
    )
    uf.to_parquet(config.ARQUIVO_GOLD_UF, index=False)
    logging.info(
        "Gravados: %s, %s, %s",
        config.ARQUIVO_GOLD_MUNICIPAL.name,
        config.ARQUIVO_GOLD_MUNICIPAL_CSV.name,
        config.ARQUIVO_GOLD_UF.name,
    )
    return gold, uf


if __name__ == "__main__":
    construir_potencial()
