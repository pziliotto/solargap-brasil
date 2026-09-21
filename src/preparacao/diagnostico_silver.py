"""
PROJETO: SolarGap Brasil
ARQUIVO: diagnostico_silver.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/09/2026
ATUALIZAÇÃO: 22/09/2026 — seções 5 a 7 (tipo de geração, REBR, código municipal)

DESCRIÇÃO:
    Investiga achados da primeira execução do construir_silver.py:
        1. 73.501 registros sem fonte de geração (99,8% no MA);
        2. 41 registros com potência igual a zero (todos no PR);
        3. 1 registro sem UF (código municipal com 6 dígitos);
        5. se SigTipoGeracao permite recuperar a fonte dos registros sem fonte;
        6. onde aparece a classe de consumo 'REBR';
        7. quantidade de dígitos do código municipal em toda a base.

    O objetivo é decidir, com evidência, se cada grupo deve ser recuperado,
    descartado ou mantido — e documentar a decisão no Data Summary Report.

OBS. DE USO:
    Rodar a partir da raiz, depois do construir_silver:
        python -m src.preparacao.diagnostico_silver
"""

import pandas as pd

from src.data_acquisition.coletor_base import obter_project_root
from src.preparacao import esquema

PROJECT_ROOT = obter_project_root(__file__)
SILVER = PROJECT_ROOT / "data" / "interim" / "mmgd_silver.parquet"

pd.set_option("display.width", 160)

silver = pd.read_parquet(SILVER)
sem_fonte = silver[silver["fonte_geracao"].isna()]
solar = silver[silver["fonte_geracao"] == esquema.FONTE_SOLAR]


def titulo(texto: str) -> None:
    print(f"\n{'═' * 70}\n{texto}\n{'═' * 70}")


# 1. Registros sem fonte de geração
titulo(f"1. SEM FONTE DE GERAÇÃO — {len(sem_fonte)} registros")
print("\nPor UF (10 maiores):")
print(sem_fonte["sigla_uf"].value_counts().head(10).to_string())

# 2. Potência nula ou <= 0
potencia = silver[silver["potencia_kw"].isna() | (silver["potencia_kw"] <= 0)]
titulo(f"2. POTÊNCIA NULA OU <= 0 — {len(potencia)} registros")
print(potencia["sigla_uf"].value_counts().to_string())

# 3. UF fora do cadastro
uf_fora = silver[~silver["sigla_uf"].isin(list(esquema.UFS))]
titulo(f"3. UF FORA DO CADASTRO — {len(uf_fora)} registro(s)")
print(uf_fora.to_string())

# 5. SigTipoGeracao permite recuperar a fonte?
titulo("5. TIPO DE GERAÇÃO (SigTipoGeracao)")
print("\nNos registros SEM fonte:")
print(sem_fonte["tipo_geracao"].value_counts(dropna=False).to_string())
print("\nNos registros com fonte 'Radiação solar':")
print(solar["tipo_geracao"].value_counts(dropna=False).to_string())
print("\nNos registros com QUALQUER OUTRA fonte:")
outras = silver[
    silver["fonte_geracao"].notna() & (silver["fonte_geracao"] != esquema.FONTE_SOLAR)
]
print(outras["tipo_geracao"].value_counts(dropna=False).to_string())

# 6. Classe de consumo 'REBR'
rebr = silver[silver["classe_consumo"] == "REBR"]
titulo(f"6. CLASSE 'REBR' — {len(rebr)} registros")
print("\nPor UF:")
print(rebr["sigla_uf"].value_counts().to_string())
print("\nTodas as classes de consumo da base:")
print(silver["classe_consumo"].value_counts(dropna=False).to_string())

# 7. Dígitos do código municipal
titulo("7. DÍGITOS DO CÓDIGO MUNICIPAL")
digitos = silver["cod_municipio"].astype("string").str.len()
print(digitos.value_counts(dropna=False).sort_index().to_string())

prefixo_uf = silver["cod_municipio"] // 100_000
com_uf = silver["cod_uf"].notna() & (digitos == 7)
divergentes = int((prefixo_uf[com_uf] != silver.loc[com_uf, "cod_uf"]).sum())
print(f"\nCódigos de 7 dígitos cujo prefixo NÃO bate com cod_uf: {divergentes}")
