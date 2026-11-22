"""
PROJETO: SolarGap Brasil
ARQUIVO: potencial/fatores.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 20/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Tabela de fatores municipais que explicam a taxa de realização do potencial
    solar (TP4.5, Tarefa 3). Uma linha por município (5.570), sem imputação:
    valores ausentes ficam ausentes e são relatados.

REGRA CENTRAL — SEM VAZAMENTO DO ALVO:
    Nenhuma variável vem da MMGD. A composição por classe da MMGD fica só como
    informação descritiva no painel. A distribuidora de cada município vem de
    bases oficiais da ANEEL independentes da MMGD (IndQual Município + DEC/FEC);
    a MMGD aparece apenas na conferência da ligação, registrada no log.

VARIÁVEIS (fonte, ano):
    renda_domiciliar_pc_media / _mediana  Censo 2022, SIDRA 10295 (R$/mês)
    pct_populacao_urbana                  Censo 2022, SIDRA 9923
    pct_vab_agropecuaria                  PIB dos Municípios 2021 (VAB agro / VAB total;
                                          último ano com VAB por atividade)
    tarifa_b1_rs_mwh                      ANEEL, B1 residencial convencional, TE + TUSD,
                                          sem impostos, média das vigências 2023-2025
                                          ponderada pelos dias; município com mais de
                                          uma distribuidora: média simples
    n_distribuidoras, multi_distribuidora, distribuidoras, cooperativa,
    n_cooperativas                        ANEEL IndQual + DEC/FEC + IASC
    icms_ano_inicio_isencao, icms_meses_isencao  CONFAZ (TP3), por UF
    irradiacao_kwh_m2_dia                 NASA POWER 2023-2025 (Tarefa 1)
    populacao_2022, log_populacao, area_km2, densidade_hab_km2  Censo 2022, SIDRA 4714
    regiao                                cadastro de UFs do projeto
    pct_area_agropecuaria                 MapBiomas Coleção 11, 2023

LIGAÇÃO DISTRIBUIDORA -> MUNICÍPIO:
    IndQual Município liga conjuntos elétricos a municípios; o DEC/FEC liga cada
    conjunto à distribuidora (SigAgente, CNPJ). Só entram conjuntos com
    indicadores a partir de config.ANO_MINIMO_CONJUNTO (conjuntos atuais).
    Filtro de adjacência: o arquivo de ligação tem pares geograficamente
    impossíveis (ex.: EPB, da Paraíba, em municípios do Maranhão). A
    distribuidora só é ligada a municípios da sua UF principal (a de mais
    municípios) ou de UFs vizinhas (config.UFS_VIZINHAS).
    Cooperativa = permissionária de distribuição (IASC, DscClassificacao), pelo
    CNPJ. As permissionárias são as cooperativas de eletrificação rural
    regularizadas como distribuidoras.

OBS. DE USO:
    python -m src.potencial.fatores   (requer coletor_fatores e as Tarefas 1 e 2)
"""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from src.data_acquisition import coletor_fatores as fontes
from src.data_acquisition.coletor_base import configurar_logging
from src.potencial import config
from src.preparacao import esquema

ARQUIVO_ICMS = config.PASTA_PROCESSED / "gold_icms_uf.csv"
ARQUIVO_SILVER_MMGD = config.PROJECT_ROOT / "data" / "interim" / "mmgd_silver.parquet"

CLASSE_AGROPECUARIA_MAPBIOMAS = "3. Farming"

COLUNAS_GOLD = [
    "cod_ibge",
    "nome",
    "uf",
    "regiao",
    "renda_domiciliar_pc_media",
    "renda_domiciliar_pc_mediana",
    "pct_populacao_urbana",
    "pct_vab_agropecuaria",
    "tarifa_b1_rs_mwh",
    "n_distribuidoras",
    "multi_distribuidora",
    "distribuidoras",
    "cooperativa",
    "n_cooperativas",
    "icms_ano_inicio_isencao",
    "icms_meses_isencao",
    "irradiacao_kwh_m2_dia",
    "populacao_2022",
    "log_populacao",
    "area_km2",
    "densidade_hab_km2",
    "pct_area_agropecuaria",
]
# Variáveis relatadas no diagnóstico de ausentes (identificação fica de fora)
VARIAVEIS = [c for c in COLUNAS_GOLD if c not in ("cod_ibge", "nome", "uf")]


# ═══════════════════ SIDRA (view=flat) ═══════════════════


def ler_sidra_flat(caminho: Path) -> pd.DataFrame:
    """JSON view=flat do SIDRA -> tabela longa: cod_ibge, variavel, categorias, valor.

    A legenda (primeiro registro) dá o significado das chaves D1C, D2C...; a do
    município e a da variável são localizadas pelo texto, sem fixar posições.
    Valores especiais do SIDRA ("-", "...", "X") viram NaN.
    """
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    legenda, registros = dados[0], dados[1:]
    chaves = {texto: chave for chave, texto in legenda.items()}
    tabela = pd.DataFrame(registros)
    resultado = pd.DataFrame(
        {
            "cod_ibge": tabela[chaves["Município (Código)"]].astype(str),
            "variavel": tabela[chaves["Variável (Código)"]].astype(str),
            "valor": pd.to_numeric(tabela["V"], errors="coerce"),
        }
    )
    for texto, chave in chaves.items():
        if texto.endswith("(Código)") and texto not in (
            "Município (Código)",
            "Variável (Código)",
            "Ano (Código)",
            "Nível Territorial (Código)",
            "Unidade de Medida (Código)",
        ):
            resultado[texto.replace(" (Código)", "")] = tabela[chave].astype(str)
    return resultado


def renda(caminho: Path) -> pd.DataFrame:
    longo = ler_sidra_flat(caminho)
    largo = longo.pivot_table(
        index="cod_ibge", columns="variavel", values="valor", dropna=False
    )
    return pd.DataFrame(
        {
            "renda_domiciliar_pc_media": largo.get("13431"),
            "renda_domiciliar_pc_mediana": largo.get("13534"),
        }
    ).reset_index()


def urbanizacao(caminho: Path) -> pd.DataFrame:
    longo = ler_sidra_flat(caminho)
    largo = longo.pivot_table(
        index="cod_ibge", columns="Situação do domicílio", values="valor", dropna=False
    )
    pct = largo["1"] / largo["6795"] * 100  # 1 = urbana, 6795 = total
    return pct.rename("pct_populacao_urbana").reset_index()


def populacao_area_densidade(caminho: Path) -> pd.DataFrame:
    longo = ler_sidra_flat(caminho)
    largo = longo.pivot_table(
        index="cod_ibge", columns="variavel", values="valor", dropna=False
    )
    resultado = pd.DataFrame(
        {
            "populacao_2022": largo["93"],
            "area_km2": largo["6318"],
            "densidade_hab_km2": largo["614"],
        }
    )
    resultado["log_populacao"] = np.log(resultado["populacao_2022"])
    return resultado.reset_index()


# ═══════════════════ PIB dos Municípios ═══════════════════


def ler_pib(caminho_zip: Path, ano: int = config.ANO_PIB) -> pd.DataFrame:
    """Recorte do ano: cod_ibge, VAB agropecuária e VAB total (R$ mil).

    As colunas da planilha têm quebras de linha no nome; são localizadas pelo
    início do texto.
    """
    with zipfile.ZipFile(caminho_zip) as arquivo_zip:
        nome = next(n for n in arquivo_zip.namelist() if n.endswith(".xlsx"))
        with arquivo_zip.open(nome) as planilha:
            pib = pd.read_excel(planilha)

    def coluna(prefixo: str) -> str:
        return next(c for c in pib.columns if str(c).startswith(prefixo))

    recorte = pib[pib["Ano"] == ano]
    return pd.DataFrame(
        {
            "cod_ibge": recorte[coluna("Código do Município")].astype(str),
            "vab_agropecuaria_mil": recorte[
                coluna("Valor adicionado bruto da Agropecuária")
            ],
            "vab_total_mil": recorte[coluna("Valor adicionado bruto total")],
        }
    ).reset_index(drop=True)


def participacao_agro(pib: pd.DataFrame) -> pd.DataFrame:
    pct = pib["vab_agropecuaria_mil"] / pib["vab_total_mil"] * 100
    return pd.DataFrame({"cod_ibge": pib["cod_ibge"], "pct_vab_agropecuaria": pct})


# ═══════════════════ MapBiomas ═══════════════════


def ler_mapbiomas(caminho_zip: Path, ano: int = config.ANO_MAPBIOMAS) -> pd.DataFrame:
    """Área agropecuária e total (ha) por município, somando os biomas."""
    coluna_ano = f"y{ano}"
    with zipfile.ZipFile(caminho_zip) as arquivo_zip:
        nome = next(n for n in arquivo_zip.namelist() if n.endswith(".xlsx"))
        with arquivo_zip.open(nome) as planilha:
            cobertura = pd.read_excel(
                planilha,
                sheet_name="COVERAGE_11",
                usecols=["geocode", "class_level_1", coluna_ano],
                dtype={"geocode": str},
            )
    return pct_area_agropecuaria(cobertura, coluna_ano)


def pct_area_agropecuaria(cobertura: pd.DataFrame, coluna_ano: str) -> pd.DataFrame:
    cobertura = cobertura.dropna(subset=["geocode"])
    total = cobertura.groupby("geocode")[coluna_ano].sum()
    agro = (
        cobertura[cobertura["class_level_1"] == CLASSE_AGROPECUARIA_MAPBIOMAS]
        .groupby("geocode")[coluna_ano]
        .sum()
    )
    pct = (agro.reindex(total.index, fill_value=0) / total * 100).rename(
        "pct_area_agropecuaria"
    )
    pct.index = pct.index.str.strip().str.zfill(7)
    return pct.rename_axis("cod_ibge").reset_index()


# ═══════════════════ Tarifa por distribuidora ═══════════════════


def tarifa_b1_por_distribuidora(
    tarifas: pd.DataFrame, janela: tuple[str, str] = config.JANELA_TARIFA
) -> pd.DataFrame:
    """TE + TUSD (R$/MWh) da B1 residencial convencional, média ponderada pelos
    dias de cada vigência dentro da janela. Sem impostos (é assim que a ANEEL
    publica as tarifas de aplicação)."""
    b1 = tarifas[
        (tarifas["DscSubGrupo"] == "B1")
        & (tarifas["DscModalidadeTarifaria"] == "Convencional")
        & (tarifas["DscClasse"] == "Residencial")
        & (tarifas["DscSubClasse"] == "Residencial")
        & (tarifas["DscDetalhe"] == "Não se aplica")
        & (tarifas["DscBaseTarifaria"] == "Tarifa de Aplicação")
        & (tarifas["DscUnidadeTerciaria"] == "MWh")
    ].copy()
    inicio, fim = pd.Timestamp(janela[0]), pd.Timestamp(janela[1])
    b1["ini"] = pd.to_datetime(b1["DatInicioVigencia"]).clip(lower=inicio)
    b1["fim"] = pd.to_datetime(b1["DatFimVigencia"]).clip(upper=fim)
    b1 = b1[b1["fim"] >= b1["ini"]]
    b1["dias"] = (b1["fim"] - b1["ini"]).dt.days + 1
    b1["tarifa"] = b1["VlrTE"] + b1["VlrTUSD"]
    b1["cnpj"] = b1["NumCNPJDistribuidora"].astype("int64").astype(str).str.zfill(14)

    agrupado = b1.groupby("cnpj")
    resultado = pd.DataFrame(
        {
            "sig_agente_tarifa": agrupado["SigAgente"].agg(
                lambda s: s.str.strip().iloc[-1]
            ),
            "tarifa_b1_rs_mwh": agrupado.apply(
                lambda g: np.average(g["tarifa"], weights=g["dias"]),
                include_groups=False,
            ),
            "dias_cobertos": agrupado["dias"].sum(),
            "n_vigencias": agrupado.size(),
        }
    )
    resultado["dias_janela"] = (fim - inicio).days + 1
    return resultado.reset_index()


# ═══════════════════ Distribuidora -> município ═══════════════════


def conjuntos_atuais(dec_fec: pd.DataFrame, ano_minimo: int) -> pd.DataFrame:
    """Conjunto -> distribuidora (SigAgente, CNPJ), só conjuntos com indicador
    a partir de ano_minimo."""
    recentes = dec_fec[dec_fec["AnoIndice"] >= ano_minimo]
    return (
        recentes.assign(
            sig_agente=recentes["SigAgente"].astype(str).str.strip(),
            cnpj=recentes["NumCNPJ"].astype("int64").astype(str).str.zfill(14),
            conjunto=recentes["IdeConjUndConsumidoras"].astype("int64"),
        )
        .drop_duplicates("conjunto")[["conjunto", "sig_agente", "cnpj"]]
        .reset_index(drop=True)
    )


def ligar_distribuidoras(
    indqual: pd.DataFrame, conjuntos: pd.DataFrame
) -> pd.DataFrame:
    """Pares município x distribuidora (sem duplicatas), com a UF do município."""
    # A UF vem do prefixo do código IBGE: SigUF do arquivo tem lacunas.
    sigla_por_cod = {cod: sigla for sigla, (cod, _) in esquema.UFS.items()}
    cod_ibge = indqual["CodMunicipio"].astype(str).str.strip().str.zfill(7)
    ligacao = indqual.assign(
        conjunto=indqual["IdeConjUnidConsumidoras"].astype("int64"),
        cod_ibge=cod_ibge,
        uf=cod_ibge.str[:2].astype(int).map(sigla_por_cod),
    ).merge(conjuntos, on="conjunto", how="inner")
    return ligacao.drop_duplicates(["cod_ibge", "cnpj"])[
        ["cod_ibge", "uf", "cnpj", "sig_agente"]
    ].reset_index(drop=True)


def filtrar_adjacencia(
    pares: pd.DataFrame, vizinhas: dict[str, set[str]] = config.UFS_VIZINHAS
) -> pd.DataFrame:
    """Mantém o par se a UF do município for a UF principal da distribuidora
    (a de mais municípios ligados) ou vizinha dela. Marca uf_principal e
    descartado_adjacencia em vez de apagar silenciosamente."""
    contagem = pares.groupby(["cnpj", "uf"]).size().rename("n").reset_index()
    principal = (
        contagem.sort_values(["cnpj", "n", "uf"], ascending=[True, False, True])
        .drop_duplicates("cnpj")
        .set_index("cnpj")["uf"]
    )
    resultado = pares.assign(uf_principal=pares["cnpj"].map(principal))
    valido = [
        uf == principal_uf or uf in vizinhas.get(principal_uf, set())
        for uf, principal_uf in zip(resultado["uf"], resultado["uf_principal"])
    ]
    resultado["descartado_adjacencia"] = ~pd.Series(valido, index=resultado.index)
    return resultado


def classificar_cooperativas(iasc: pd.DataFrame) -> pd.Series:
    """CNPJ -> True se permissionária (cooperativa), pela classificação mais recente."""
    iasc = iasc.assign(
        cnpj=iasc["NumCNPJ"].astype(str).str.strip().str.zfill(14),
        ano=pd.to_numeric(iasc["NumAno"], errors="coerce"),
    ).sort_values("ano")
    ultima = iasc.drop_duplicates("cnpj", keep="last").set_index("cnpj")
    return ultima["DscClassificacao"].str.strip().eq("Permissionária")


def fatores_distribuidora(
    pares: pd.DataFrame, tarifas: pd.DataFrame, cooperativas: pd.Series
) -> pd.DataFrame:
    """Uma linha por município: tarifa (média simples), contagens e flags."""
    validos = pares[~pares["descartado_adjacencia"]].merge(
        tarifas[["cnpj", "tarifa_b1_rs_mwh"]], on="cnpj", how="left"
    )
    validos["eh_cooperativa"] = validos["cnpj"].map(cooperativas)
    agrupado = validos.groupby("cod_ibge")
    resultado = pd.DataFrame(
        {
            "tarifa_b1_rs_mwh": agrupado["tarifa_b1_rs_mwh"].mean(),
            "n_distribuidoras": agrupado["cnpj"].nunique(),
            "distribuidoras": agrupado["sig_agente"].agg(
                lambda s: ";".join(sorted(set(s)))
            ),
            "n_cooperativas": agrupado["eh_cooperativa"].agg(
                lambda s: int(s.fillna(False).astype(bool).sum())
            ),
        }
    )
    resultado["multi_distribuidora"] = resultado["n_distribuidoras"] > 1
    resultado["cooperativa"] = resultado["n_cooperativas"] > 0
    return resultado.reset_index()


# ═══════════════════ ICMS ═══════════════════


def icms_por_uf(caminho: Path = ARQUIVO_ICMS) -> pd.DataFrame:
    icms = pd.read_csv(caminho, sep=";")
    return icms.rename(
        columns={
            "sigla_uf": "uf",
            "ano_inicio_efeitos": "icms_ano_inicio_isencao",
            "meses_desde_inicio": "icms_meses_isencao",
        }
    )[["uf", "icms_ano_inicio_isencao", "icms_meses_isencao"]]


# ═══════════════════ Montagem ═══════════════════


def montar_fatores(base: pd.DataFrame, partes: list[pd.DataFrame]) -> pd.DataFrame:
    """Junta as partes à base de 5.570 municípios (left join, sem imputar).

    Cada parte precisa ter cod_ibge único; partes com UF (ICMS) juntam por uf.
    """
    fatores = base[["cod_ibge", "nome", "uf"]].copy()
    fatores["regiao"] = fatores["uf"].map(esquema.REGIAO_POR_UF)
    for parte in partes:
        chave = "cod_ibge" if "cod_ibge" in parte.columns else "uf"
        if parte[chave].duplicated().any():
            raise ValueError(f"Chave {chave} duplicada em {list(parte.columns)}")
        fatores = fatores.merge(parte, on=chave, how="left", validate="many_to_one")
    for coluna in ("n_distribuidoras", "n_cooperativas"):
        if coluna in fatores:
            fatores[coluna] = fatores[coluna].astype("Int64")
    for coluna in ("multi_distribuidora", "cooperativa"):
        if coluna in fatores:
            fatores[coluna] = fatores[coluna].astype("boolean")
    return fatores[[c for c in COLUNAS_GOLD if c in fatores.columns]]


def validar_fatores(fatores: pd.DataFrame) -> list[str]:
    problemas = []
    if len(fatores) != config.TOTAL_MUNICIPIOS:
        problemas.append(f"{len(fatores)} linhas (esperado {config.TOTAL_MUNICIPIOS})")
    if fatores["cod_ibge"].duplicated().any():
        problemas.append("cod_ibge duplicado")
    if not fatores["cod_ibge"].astype(str).str.fullmatch(r"\d{7}").all():
        problemas.append("cod_ibge fora do padrão de 7 dígitos")
    return problemas


def relatorio_ausentes(fatores: pd.DataFrame) -> pd.DataFrame:
    variaveis = [c for c in VARIAVEIS if c in fatores.columns]
    ausentes = fatores[variaveis].isna().sum()
    return pd.DataFrame(
        {
            "variavel": ausentes.index,
            "n_ausentes": ausentes.to_numpy(),
            "pct_ausentes": (ausentes / len(fatores) * 100).round(2).to_numpy(),
        }
    )


def conferir_com_mmgd(pares_validos: pd.DataFrame) -> float:
    """Conferência (não é variável do modelo): em quantos municípios a
    distribuidora mais frequente na MMGD está entre as da ligação oficial."""
    silver = pd.read_parquet(
        ARQUIVO_SILVER_MMGD,
        columns=["cod_municipio", "distribuidora"],
        filters=[("fonte_geracao", "==", esquema.FONTE_SOLAR)],
    )
    principal = (
        silver.dropna()
        .groupby("cod_municipio")["distribuidora"]
        .agg(lambda s: s.mode().iloc[0])
    )
    principal.index = principal.index.astype("int64").astype(str)
    oficial = pares_validos.groupby("cod_ibge")["sig_agente"].agg(set)
    comuns = principal.index.intersection(oficial.index)
    acertos = sum(principal[c] in oficial[c] for c in comuns)
    return acertos / len(comuns) if len(comuns) else float("nan")


# ═══════════════════ Execução ═══════════════════


def _pib_em_cache() -> pd.DataFrame:
    if config.ARQUIVO_PIB_RECORTE.exists():
        return pd.read_parquet(config.ARQUIVO_PIB_RECORTE)
    pib = ler_pib(fontes.FONTES["pib"]["arquivo"])
    config.PASTA_INTERIM_POTENCIAL.mkdir(parents=True, exist_ok=True)
    pib.to_parquet(config.ARQUIVO_PIB_RECORTE, index=False)
    return pib


def construir_fatores() -> pd.DataFrame:
    configurar_logging("POTENCIAL_FATORES", config.PASTA_LOGS)
    arquivos = {nome: fonte["arquivo"] for nome, fonte in fontes.FONTES.items()}
    faltando = [nome for nome, caminho in arquivos.items() if not caminho.exists()]
    if faltando:
        raise FileNotFoundError(
            f"Fontes ausentes no cache: {faltando}. "
            "Rode antes: python -m src.data_acquisition.coletor_fatores"
        )

    # Distribuidora -> município e tarifa
    tarifas = tarifa_b1_por_distribuidora(pd.read_parquet(arquivos["tarifas"]))
    conjuntos = conjuntos_atuais(
        pd.read_parquet(
            arquivos["dec_fec"],
            columns=["SigAgente", "NumCNPJ", "IdeConjUndConsumidoras", "AnoIndice"],
        ),
        config.ANO_MINIMO_CONJUNTO,
    )
    indqual = pd.read_csv(
        arquivos["indqual_municipio"], sep=";", encoding="latin1", dtype=str
    )
    pares = filtrar_adjacencia(ligar_distribuidoras(indqual, conjuntos))
    iasc = pd.read_csv(
        arquivos["iasc"],
        sep=";",
        encoding="utf-8",
        dtype=str,
        usecols=["NumAno", "DscClassificacao", "NumCNPJ"],
    )
    cooperativas = classificar_cooperativas(iasc)
    pares["eh_cooperativa"] = pares["cnpj"].map(cooperativas)
    pares["tem_tarifa"] = pares["cnpj"].isin(tarifas["cnpj"])

    descartados = pares[pares["descartado_adjacencia"]]
    logging.info(
        "Ligação oficial: %d pares município x distribuidora; %d descartados pela "
        "adjacência (%s)",
        len(pares),
        len(descartados),
        descartados.groupby("sig_agente")["uf"]
        .agg(lambda s: ",".join(sorted(set(s))))
        .to_dict(),
    )
    sem_tarifa = sorted(set(pares.loc[~pares["tem_tarifa"], "sig_agente"]))
    sem_classificacao = sorted(
        set(pares.loc[pares["eh_cooperativa"].isna(), "sig_agente"])
    )
    logging.info("Distribuidoras sem tarifa B1: %s", sem_tarifa or "nenhuma")
    logging.info(
        "Distribuidoras sem classificação IASC: %s", sem_classificacao or "nenhuma"
    )
    logging.info(
        "Conferência com a MMGD (só validação): distribuidora principal da MMGD está "
        "na ligação oficial em %.1f%% dos municípios",
        100 * conferir_com_mmgd(pares[~pares["descartado_adjacencia"]]),
    )

    config.PASTA_INTERIM_POTENCIAL.mkdir(parents=True, exist_ok=True)
    pares.to_parquet(config.ARQUIVO_DISTRIBUIDORA_MUNICIPIO, index=False)
    tarifas.to_parquet(config.ARQUIVO_TARIFA_DISTRIBUIDORA, index=False)

    # Demais fontes
    base = pd.read_parquet(config.ARQUIVO_PONTOS)
    irradiacao = pd.read_parquet(config.ARQUIVO_IRRADIACAO)[
        ["cod_ibge", "irradiacao_kwh_m2_dia"]
    ]
    logging.info("Lendo MapBiomas (planilha grande, ~1 min)...")
    partes = [
        renda(arquivos["renda"]),
        urbanizacao(arquivos["urbanizacao"]),
        participacao_agro(_pib_em_cache()),
        fatores_distribuidora(pares, tarifas, cooperativas),
        icms_por_uf(),
        irradiacao,
        populacao_area_densidade(arquivos["area_densidade"]),
        ler_mapbiomas(arquivos["mapbiomas"]),
    ]
    fatores = montar_fatores(base, partes)

    problemas = validar_fatores(fatores)
    if problemas:
        raise ValueError("Fatores reprovados: " + "; ".join(problemas))

    ausentes = relatorio_ausentes(fatores)
    ausentes.to_csv(config.ARQUIVO_AUSENTES_FATORES, sep=";", index=False)
    logging.info("Valores ausentes por variável:\n%s", ausentes.to_string(index=False))
    logging.info(
        "Municípios com mais de uma distribuidora: %d | com cooperativa: %d",
        int(fatores["multi_distribuidora"].fillna(False).sum()),
        int(fatores["cooperativa"].fillna(False).sum()),
    )
    logging.info("\n%s", fatores[VARIAVEIS].describe().T.round(2).to_string())

    config.PASTA_PROCESSED.mkdir(parents=True, exist_ok=True)
    fatores.to_parquet(config.ARQUIVO_GOLD_FATORES, index=False)
    logging.info("Gravado: %s (%d x %d)", config.ARQUIVO_GOLD_FATORES, *fatores.shape)
    return fatores


if __name__ == "__main__":
    construir_fatores()
