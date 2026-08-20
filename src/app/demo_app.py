"""
PROJETO: SolarGap Brasil
ARQUIVO: demo_app.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 20/08/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Aplicativo demo para uma visualização básica dos dados que serão utilizados,
    contendo os seguintes campos, solicitados pelo avaliador:
        - Título do projeto
        - Descrição do problema de negócio
        - Objetivos do projeto
        - Links úteis
        - Tabela de dados

"""

import pandas as pd
import streamlit as st

from src.data_acquisition.coletor_base import obter_project_root

# 1. Configuração da página
st.set_page_config(page_title="SolarGap - Brasil", page_icon="☀️", layout="centered")

# 2. Elementos de exibição base
st.title(":green[SolarGap - Brasil]")
st.caption("Onde está o próximo mercado solar?")

st.divider()

# 3. Problema de negócio e objetivo
st.header("❓O problema sendo avaliado")
st.markdown(
    """
    <p style ='text-align: justify; font-size: 1.05rem; line-height: 1.6;'>
        Desde a promulgação da Lei 14.300/2022 (Marco Legal da Geração Distribuída), a geração distribuída de energia solar cresceu de forma acentuada no Brasil. No entanto, há indícios de que esse crescimento não se distribui de forma equânime entre os estados — o que pode aprofundar desigualdades regionais de acesso à transição energética.
    </p>
""",
    unsafe_allow_html=True,
)
st.header("🔬 O objetivo do projeto")
st.markdown(
    """
    <p style ='text-align: justify; font-size: 1.05rem; line-height: 1.6;'>
        O SolarGap Brasil propõe mapear e quantificar essa disparidade, transformando dados públicos da ANEEL e do IBGE em um painel interativo capaz de identificar quais estados estão liderando e quais estão ficando para trás na adoção de energia solar distribuída — revelando, ao mesmo tempo, onde estão as oportunidades ainda não exploradas pelo mercado solar.
    </p>
""",
    unsafe_allow_html=True,
)

st.divider()

# 4. Links úteis
st.sidebar.markdown("""
**Fontes de dados**
- [ANEEL — Geração Distribuída](https://dadosabertos.aneel.gov.br)
- [ANEEL - Power BI MMGD](https://app.powerbi.com/view?r=eyJrIjoiY2VmMmUwN2QtYWFiOS00ZDE3LWI3NDMtZDk0NGI4MGU2NTkxIiwidCI6IjQwZDZmOWI4LWVjYTctNDZhMi05MmQ0LWVhNGU5YzAxNzBlMSIsImMiOjR9)
- [IBGE — Censo 2022](https://www.ibge.gov.br/estatisticas/sociais/populacao/22827-censo-2022.html)
- [Lei 14.300/2022](https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/lei/l14300.htm)

""")

# 5. Tabelas

# 5.1 Organização dos dados
PROJECT_ROOT = obter_project_root(__file__)
PASTA_RAW = PROJECT_ROOT / "data" / "raw"

ibge_uf = f"{PASTA_RAW}/demografico_uf_2022.json"
ibge_municipio = f"{PASTA_RAW}/demografico_municipio_2022.json"
mmgd = f"{PASTA_RAW}/amostra_mmgd.csv"

df_ibge_uf = pd.read_json(ibge_uf)
df_ibge_municipio = pd.read_json(ibge_municipio)
df_mmgd = pd.read_csv(mmgd, sep=";")

# 5.2 Titulo
st.header("Amostra de Dados")

# 5.3 IBGE UF
st.subheader("IBGE - Unidades Federativas")
st.dataframe(df_ibge_uf.head(10), width="stretch", hide_index=True)

# 5.4 IBGE MUNICIPIOS
st.subheader("IBGE - Municípios")
st.dataframe(df_ibge_municipio.head(10), width="stretch", hide_index=True)

# 5.5 ANEEL
st.subheader("ANEEL - Geração Distribuída")
st.dataframe(df_mmgd.head(10), width="stretch", hide_index=True)
