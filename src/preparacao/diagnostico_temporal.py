"""
PROJETO: SolarGap Brasil
ARQUIVO: diagnostico_temporal.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 20/08/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Diagnóstico temporal para validar a distribuição histórica de aderência a energia
    solar distribuída ao cruzar os dados gerados aqui com o painel oficial da ANEEL.

FONTE:
    Portal de Dados Abertos da Aneel (CKAN).

DATASET:
    "Relação de empreendimentos de Mini e Micro Geração Distribuída"

OBS.:
    O script efetua um agrupamento dos registros por ano em duas colunas chave:
     "DthAtualizaCadastralEmpreend", "AnmPeriodoReferencia"

    A segunda etapa ocorre de forma manual ao cruzar os valores que serão gerados e
    impressos no terminal com os valores apresentados no painel BI da ANEEL.

"""

import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path.cwd()  # se estiver rodando da raiz
ARQUIVO_ZIP = PROJECT_ROOT / "data" / "raw" / "empreendimento-geracao-distribuida.zip"
NOME_CSV = "empreendimento-geracao-distribuida.csv"

COLUNAS = ["DthAtualizaCadastralEmpreend", "AnmPeriodoReferencia"]

ano = Counter()
mes = Counter()
referencia = Counter()
invalidas = 0

with zipfile.ZipFile(ARQUIVO_ZIP) as z, z.open(NOME_CSV) as fluxo:
    for chunk in pd.read_csv(
        fluxo, sep=";", encoding="utf-8", dtype=str, usecols=COLUNAS, chunksize=500_000
    ):
        datas = pd.to_datetime(chunk["DthAtualizaCadastralEmpreend"], errors="coerce")
        invalidas += datas.isna().sum()
        ano.update(datas.dt.year.dropna().astype(int))
        mes.update(datas.dt.to_period("M").dropna().astype(str))
        referencia.update(chunk["AnmPeriodoReferencia"].dropna())

print("Períodos de referência distintos:", len(referencia))
print("Datas não parseadas:", invalidas)
for k in sorted(ano):
    print(k, ano[k])
