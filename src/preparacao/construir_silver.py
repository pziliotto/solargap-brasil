"""
PROJETO: SolarGap Brasil
ARQUIVO: construir_silver.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/09/2026
ATUALIZAÇÃO: 22/09/2026 — correções a partir do diagnostico_silver.py

DESCRIÇÃO:
    Constrói a camada Silver (data/interim) a partir da camada Bronze (data/raw):
        - MMGD/ANEEL: limpeza, tipagem, correções e critérios de exclusão
          documentados no Data Summary Report (seção 3.2);
        - IBGE: achatamento dos JSONs de população (UF e município) em CSV.

DECISÕES:
    - Todas as fontes de geração são mantidas. Silver é dado limpo, não dado
      recortado: o filtro de fonte solar é decisão analítica e fica na Gold.
    - A base é lida e gravada em chunks (ParquetWriter), sem acumular os
      ~4,6 milhões de registros em memória.
    - Gravação em arquivo .parcial, renomeado só ao final (mesmo padrão do
      aneel.py): uma execução interrompida nunca deixa Silver pela metade.

CORREÇÕES (evidência no diagnostico_silver.py):
    - Fonte imputada: registros sem DscFonteGeracao E sem SigTipoGeracao
      (73.501, 99,8% no MA) recebem "Radiação solar". Justificativa: 99,98%
      dos registros com fonte conhecida são solares e a distribuição de
      potência do grupo é equivalente à dos solares. A coluna
      fonte_imputada preserva a rastreabilidade e permite reverter a decisão.
    - Código municipal com 6 dígitos (sem dígito verificador) é convertido
      para 7 dígitos pela tabela do IBGE.
    - UF ausente é recuperada pelo prefixo do código municipal.

EXCLUSÕES:
    - Sem data, ano 1900 (sentinela), ano anterior a 2012 (REN 482/2012);
    - Potência nula ou <= 0: fisicamente inválida para usina conectada.

SAÍDAS:
    data/interim/mmgd_silver.parquet
    data/interim/populacao_uf_silver.csv
    data/interim/populacao_municipio_silver.csv

OBS. DE USO:
    Rodar como módulo a partir da raiz:
        python -m src.preparacao.construir_silver
"""

from __future__ import annotations

import json
import logging
import sys
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.data_acquisition.coletor_base import configurar_logging, obter_project_root
from src.preparacao import esquema
from src.preparacao.gerar_amostra import localizar_csv_no_zip

PROJECT_ROOT = obter_project_root(__file__)
PASTA_RAW = PROJECT_ROOT / "data" / "raw"
PASTA_INTERIM = PROJECT_ROOT / "data" / "interim"
PASTA_LOGS = PROJECT_ROOT / "logs"

ARQUIVO_ZIP = PASTA_RAW / "empreendimento-geracao-distribuida.zip"
ARQUIVO_IBGE_UF = PASTA_RAW / "demografico_uf_2022.json"
ARQUIVO_IBGE_MUNICIPIO = PASTA_RAW / "demografico_municipio_2022.json"

SAIDA_MMGD = PASTA_INTERIM / "mmgd_silver.parquet"
SAIDA_POP_UF = PASTA_INTERIM / "populacao_uf_silver.csv"
SAIDA_POP_MUNICIPIO = PASTA_INTERIM / "populacao_municipio_silver.csv"

TAMANHO_CHUNK = 500_000
SEPARADOR = ";"

# código IBGE da UF -> sigla (inverso do cadastro do esquema)
SIGLA_POR_COD = {cod: sigla for sigla, (cod, _) in esquema.UFS.items()}

# Esquema fixo do Parquet: garante tipos idênticos em todos os chunks.
SCHEMA_SILVER = pa.schema(
    [
        ("sigla_uf", pa.string()),
        ("cod_uf", pa.int64()),
        ("cod_municipio", pa.int64()),
        ("potencia_kw", pa.float64()),
        ("fonte_geracao", pa.string()),
        ("fonte_imputada", pa.bool_()),
        ("classe_consumo", pa.string()),
        ("tipo_geracao", pa.string()),
        ("data_conexao", pa.timestamp("ns")),
        ("ano", pa.int64()),
    ]
)


def formatar(numero: int) -> str:
    """Formata inteiros no padrão brasileiro: 4673268 -> 4.673.268."""
    return f"{numero:,}".replace(",", ".")


# ═══════════════════ IBGE ═══════════════════


def ler_ibge_flat(caminho: Path, rotulo_localidade: str) -> pd.DataFrame:
    """Lê um JSON do IBGE em view=flat e devolve código, nome e população.

    O primeiro registro do view=flat é a legenda (por isso vêm 28 registros
    no nível UF). As chaves abreviadas (D1C, D1N...) são localizadas pelo
    texto da legenda, e não fixadas no código, para não quebrar se o IBGE
    mudar a ordem das dimensões.
    """
    with open(caminho, encoding="utf-8") as arquivo:
        dados = json.load(arquivo)

    legenda, registros = dados[0], dados[1:]

    chave_codigo = next(
        (k for k, v in legenda.items() if v == f"{rotulo_localidade} (Código)"), None
    )
    chave_nome = next((k for k, v in legenda.items() if v == rotulo_localidade), None)

    if chave_codigo is None or chave_nome is None or "V" not in legenda:
        logging.error(
            "Legenda do IBGE sem as chaves esperadas para '%s'.", rotulo_localidade
        )
        logging.error("Legenda recebida: %s", legenda)
        sys.exit(1)

    df = pd.DataFrame(registros)
    return pd.DataFrame(
        {
            "codigo": pd.to_numeric(df[chave_codigo], errors="coerce").astype("Int64"),
            "nome": df[chave_nome].str.strip(),
            "populacao": pd.to_numeric(df["V"], errors="coerce").astype("Int64"),
        }
    )


def validar_populacao(df: pd.DataFrame, nivel: str, esperado: int) -> None:
    """Falha alto se a contagem de registros ou os valores não baterem."""
    if len(df) != esperado:
        logging.error("%s: esperava %d registros, obtive %d.", nivel, esperado, len(df))
        sys.exit(1)

    nulos = int(df.isna().sum().sum())
    if nulos:
        logging.error("%s: %d valores nulos após a conversão.", nivel, nulos)
        sys.exit(1)

    logging.info(
        "%s: %d registros | população total %s",
        nivel,
        len(df),
        formatar(int(df["populacao"].sum())),
    )


def construir_populacao_silver() -> pd.DataFrame:
    """Grava a população por UF e município; devolve a tabela municipal,
    usada depois para corrigir códigos municipais de 6 dígitos."""
    logging.info("--- IBGE: população ---")

    uf = ler_ibge_flat(ARQUIVO_IBGE_UF, "Unidade da Federação").rename(
        columns={"codigo": "cod_uf", "nome": "nome_uf"}
    )
    validar_populacao(uf, "UF", esquema.TOTAL_UFS)

    if set(uf["cod_uf"]) != set(SIGLA_POR_COD):
        logging.error("Códigos de UF do IBGE não batem com o cadastro do esquema.")
        sys.exit(1)

    municipio = ler_ibge_flat(ARQUIVO_IBGE_MUNICIPIO, "Município").rename(
        columns={"codigo": "cod_municipio", "nome": "nome_municipio"}
    )
    validar_populacao(municipio, "Município", 5570)

    uf.to_csv(SAIDA_POP_UF, index=False, sep=SEPARADOR, encoding="utf-8")
    municipio.to_csv(SAIDA_POP_MUNICIPIO, index=False, sep=SEPARADOR, encoding="utf-8")
    logging.info("Salvo: %s", SAIDA_POP_UF)
    logging.info("Salvo: %s", SAIDA_POP_MUNICIPIO)

    return municipio


# ═══════════════════ ANEEL / MMGD ═══════════════════


def tratar_chunk(
    chunk: pd.DataFrame, contagem: Counter, municipio_7_digitos: dict[int, int]
) -> pd.DataFrame:
    """Renomeia, tipa, corrige e filtra um bloco da base, acumulando contagens."""
    df = chunk.rename(columns=esquema.RENOMEAR_ANEEL)
    contagem["lidos"] += len(df)

    for coluna in ("sigla_uf", "fonte_geracao", "classe_consumo", "tipo_geracao"):
        df[coluna] = df[coluna].str.strip()
    df["sigla_uf"] = df["sigla_uf"].str.upper()

    # CodUFibge chega como float na origem ("35.0"); vira inteiro anulável.
    df["cod_uf"] = pd.to_numeric(df["cod_uf"], errors="coerce").astype("Int64")
    df["cod_municipio"] = pd.to_numeric(df["cod_municipio"], errors="coerce").astype(
        "Int64"
    )

    # Decimal com vírgula, padrão das bases governamentais brasileiras.
    df["potencia_kw"] = pd.to_numeric(
        df["potencia_kw"].str.replace(",", ".", regex=False), errors="coerce"
    )

    # Mesma conversão do diagnostico_temporal.py, validada contra o painel
    # oficial da ANEEL (Data Summary Report, seção 3.1).
    df["data_conexao"] = pd.to_datetime(df["data_conexao"], errors="coerce")
    df["ano"] = df["data_conexao"].dt.year.astype("Int64")

    # ── Exclusões temporais (Data Summary Report, seção 3.2) ──
    sem_data = df["ano"].isna()
    sentinela = (df["ano"] == esquema.ANO_SENTINELA).fillna(False)
    pre_marco = (df["ano"] < esquema.ANO_MINIMO).fillna(False) & ~sentinela

    contagem["sem_data"] += int(sem_data.sum())
    contagem["sentinela_1900"] += int(sentinela.sum())
    contagem["pre_2012"] += int(pre_marco.sum())

    df = df[~(sem_data | sentinela | pre_marco).astype(bool)].copy()

    # ── Correção 1: código municipal de 6 dígitos -> 7 dígitos ──
    seis_digitos = (df["cod_municipio"] < 1_000_000).fillna(False).astype(bool)
    if seis_digitos.any():
        corrigido = df.loc[seis_digitos, "cod_municipio"].map(municipio_7_digitos)
        df.loc[seis_digitos, "cod_municipio"] = corrigido.astype("Int64")
        contagem["municipio_corrigido"] += int(corrigido.notna().sum())

    # ── Correção 2: UF ausente recuperada pelo prefixo do código municipal ──
    sem_uf = (~df["sigla_uf"].isin(list(esquema.UFS))) & df["cod_municipio"].notna()
    sem_uf = sem_uf.astype(bool)
    if sem_uf.any():
        cod_uf = (df.loc[sem_uf, "cod_municipio"] // 100_000).astype("Int64")
        df.loc[sem_uf, "cod_uf"] = cod_uf
        df.loc[sem_uf, "sigla_uf"] = cod_uf.map(SIGLA_POR_COD)
        contagem["uf_recuperada"] += int(df.loc[sem_uf, "sigla_uf"].notna().sum())

    # ── Correção 3: fonte imputada quando fonte E tipo de geração são nulos ──
    imputar = (df["fonte_geracao"].isna() & df["tipo_geracao"].isna()).astype(bool)
    df["fonte_imputada"] = imputar
    df.loc[imputar, "fonte_geracao"] = esquema.FONTE_SOLAR
    contagem["fonte_imputada"] += int(imputar.sum())

    # ── Exclusão: potência nula ou <= 0 ──
    potencia_invalida = (df["potencia_kw"].isna() | (df["potencia_kw"] <= 0)).astype(
        bool
    )
    contagem["potencia_invalida"] += int(potencia_invalida.sum())
    df = df[~potencia_invalida]

    # ── Monitoramento: contado, não descartado ──
    contagem["uf_fora_cadastro"] += int((~df["sigla_uf"].isin(list(esquema.UFS))).sum())
    contagem["fonte_nula_restante"] += int(df["fonte_geracao"].isna().sum())

    contagem["mantidos"] += len(df)
    return df[SCHEMA_SILVER.names]


def registrar_resumo(contagem: Counter, fontes: Counter, imputados_uf: Counter) -> None:
    descartados = (
        contagem["sem_data"]
        + contagem["sentinela_1900"]
        + contagem["pre_2012"]
        + contagem["potencia_invalida"]
    )

    logging.info("--- Resumo da Silver MMGD ---")
    logging.info("Registros lidos ..............: %s", formatar(contagem["lidos"]))
    logging.info("Descartados — sem data .......: %s", formatar(contagem["sem_data"]))
    logging.info(
        "Descartados — ano 1900 .......: %s", formatar(contagem["sentinela_1900"])
    )
    logging.info("Descartados — antes 2012 .....: %s", formatar(contagem["pre_2012"]))
    logging.info(
        "Descartados — potência <= 0 ..: %s", formatar(contagem["potencia_invalida"])
    )
    logging.info("Registros mantidos ...........: %s", formatar(contagem["mantidos"]))
    logging.info(
        "Conferência (mantidos + descartados = lidos): %s",
        "OK"
        if contagem["mantidos"] + descartados == contagem["lidos"]
        else "DIVERGENTE",
    )

    logging.info("--- Correções aplicadas ---")
    logging.info(
        "Código municipal 6 -> 7 dígitos: %s", formatar(contagem["municipio_corrigido"])
    )
    logging.info(
        "UF recuperada pelo município ..: %s", formatar(contagem["uf_recuperada"])
    )
    logging.info(
        "Fonte imputada como solar .....: %s", formatar(contagem["fonte_imputada"])
    )
    for uf, quantidade in imputados_uf.most_common(5):
        logging.info("    %-4s %s", uf, formatar(quantidade))

    logging.info("--- Monitoramento (esperado: zero) ---")
    logging.info(
        "UF fora do cadastro .....: %s", formatar(contagem["uf_fora_cadastro"])
    )
    logging.info(
        "Fonte ainda nula ........: %s", formatar(contagem["fonte_nula_restante"])
    )

    logging.info("--- Registros mantidos por fonte de geração ---")
    for fonte, quantidade in fontes.most_common():
        logging.info("  %-30s %s", fonte, formatar(quantidade))

    if esquema.FONTE_SOLAR not in fontes:
        logging.warning(
            "FONTE_SOLAR ('%s') não apareceu na base — a Gold ficaria vazia.",
            esquema.FONTE_SOLAR,
        )


def construir_mmgd_silver(municipio_7_digitos: dict[int, int]) -> None:
    logging.info("--- ANEEL: MMGD ---")
    nome_csv = localizar_csv_no_zip(ARQUIVO_ZIP)

    contagem: Counter = Counter()
    fontes: Counter = Counter()
    imputados_uf: Counter = Counter()
    temporario = SAIDA_MMGD.with_suffix(".parquet.parcial")
    writer: pq.ParquetWriter | None = None

    try:
        with (
            zipfile.ZipFile(ARQUIVO_ZIP) as arquivo_zip,
            arquivo_zip.open(nome_csv) as fluxo,
        ):
            leitor = pd.read_csv(
                fluxo,
                sep=SEPARADOR,
                encoding="utf-8",
                dtype=str,
                usecols=esquema.COLUNAS_ANEEL,
                chunksize=TAMANHO_CHUNK,
            )
            writer = pq.ParquetWriter(temporario, SCHEMA_SILVER)

            for numero, chunk in enumerate(leitor, start=1):
                df = tratar_chunk(chunk, contagem, municipio_7_digitos)
                fontes.update(df["fonte_geracao"].value_counts().to_dict())
                imputados_uf.update(
                    df.loc[df["fonte_imputada"], "sigla_uf"].value_counts().to_dict()
                )
                writer.write_table(
                    pa.Table.from_pandas(df, schema=SCHEMA_SILVER, preserve_index=False)
                )
                logging.info(
                    "  chunk %d — %s registros lidos até agora",
                    numero,
                    formatar(contagem["lidos"]),
                )

        writer.close()
        writer = None
        temporario.replace(SAIDA_MMGD)

    finally:
        # Só entra aqui com writer aberto se algo falhou no meio do caminho.
        if writer is not None:
            writer.close()
            temporario.unlink(missing_ok=True)
            logging.error("Execução interrompida — arquivo parcial removido.")

    tamanho_mb = SAIDA_MMGD.stat().st_size / (1024 * 1024)
    logging.info("Salvo: %s (%.1f MB)", SAIDA_MMGD, tamanho_mb)
    registrar_resumo(contagem, fontes, imputados_uf)


# ═══════════════════ Execução ═══════════════════


def construir_silver() -> None:
    caminho_log = configurar_logging("SILVER", PASTA_LOGS)
    logging.info("=" * 70)
    logging.info("Construção da camada Silver")
    logging.info("Raiz do projeto: %s", PROJECT_ROOT)

    PASTA_INTERIM.mkdir(parents=True, exist_ok=True)

    # IBGE primeiro: leva segundos e, se houver problema, falha antes
    # dos minutos de leitura da base da ANEEL.
    municipio = construir_populacao_silver()

    # O código IBGE de 7 dígitos é o de 6 dígitos + dígito verificador.
    municipio_7_digitos = {
        int(cod) // 10: int(cod) for cod in municipio["cod_municipio"]
    }

    construir_mmgd_silver(municipio_7_digitos)

    logging.info("Log da sessão: %s", caminho_log)
    logging.info("Concluído.")
    logging.info("=" * 70)


if __name__ == "__main__":
    construir_silver()
