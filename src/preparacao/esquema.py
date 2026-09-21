"""
PROJETO: SolarGap Brasil
ARQUIVO: esquema.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/09/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Constantes compartilhadas entre as camadas Silver e Gold e, a partir da etapa 2,
    pelos scrapers. Esse módulo NÃO contém lógica de tratamento: centraliza nomes de
    colunas, cortes temporais e o cadastro das UFs para que nenhum desses valores seja
    digitado à mão em mais de um arquivo.

OBS.:
    Se a ANEEL renomear uma coluna ou o cadastro de UFs precisar de ajuste a correção
    acontece só aqui.
"""

from __future__ import annotations

from src.data_acquisition.aneel import COLUNAS_SENSIVEIS

# ═══════════════════ Colunas da base ANEEL ═══════════════════

# Colunas lidas do CSV original (parâmetro usecols do pandas).
# NumCPFCNPJ e NomTitularEmpreendimento ficam de fora de propósito:
# o dado pessoal nunca é carregado em memória (minimização - LGPD)
COLUNAS_ANEEL = [
    "SigUF",
    "CodUFibge",
    "CodMunicipioIbge",
    "MdaPotenciaInstaladaKW",
    "DscFonteGeracao",
    "DscClasseConsumo",
    "DthAtualizaCadastralEmpreend",
    "SigTipoGeracao",
]

# Renomeação para snake_case na camada Silver.
# DthAtualizaCadastralEmpreend vira data_conexao por que a própria ANEEL usa o
# campo como "Ano de Conexão" no painell oficial (Data Summary Report, 3.1)
RENOMEAR_ANEEL = {
    "SigUF": "sigla_uf",
    "CodUFibge": "cod_uf",
    "CodMunicipioIbge": "cod_municipio",
    "MdaPotenciaInstaladaKW": "potencia_kw",
    "DscFonteGeracao": "fonte_geracao",
    "DscClasseConsumo": "classe_consumo",
    "DthAtualizaCadastralEmpreend": "data_conexao",
    "SigTipoGeracao": "tipo_geracao",
}

# Mantido aqui para consulta; os scripts antigos têm cópia própria.
COLUNAS_SENSIVEIS = ["NumCPFCNPJ", "NomTitularEmpreendimento"]

# ═══════════════════ Filtros e cortes ═══════════════════

FONTE_SOLAR = "Radiação solar"

ANO_SENTINELA = 1900  # Data de preenchimento sem significado real
ANO_MINIMO = 2012  # REN nº 482/2012 - início do marco regulatório da MMGD
ANO_PARCIAL = 2026  # ano corrente, dados até a referência 08/2026

# ═══════════════════ Cadastro das UFs ═══════════════════


# sigla -> (código IBGE, nome)
UFS = {
    "RO": (11, "Rondônia"),
    "AC": (12, "Acre"),
    "AM": (13, "Amazonas"),
    "RR": (14, "Roraima"),
    "PA": (15, "Pará"),
    "AP": (16, "Amapá"),
    "TO": (17, "Tocantins"),
    "MA": (21, "Maranhão"),
    "PI": (22, "Piauí"),
    "CE": (23, "Ceará"),
    "RN": (24, "Rio Grande do Norte"),
    "PB": (25, "Paraíba"),
    "PE": (26, "Pernambuco"),
    "AL": (27, "Alagoas"),
    "SE": (28, "Sergipe"),
    "BA": (29, "Bahia"),
    "MG": (31, "Minas Gerais"),
    "ES": (32, "Espírito Santo"),
    "RJ": (33, "Rio de Janeiro"),
    "SP": (35, "São Paulo"),
    "PR": (41, "Paraná"),
    "SC": (42, "Santa Catarina"),
    "RS": (43, "Rio Grande do Sul"),
    "MS": (50, "Mato Grosso do Sul"),
    "MT": (51, "Mato Grosso"),
    "GO": (52, "Goiás"),
    "DF": (53, "Distrito Federal"),
}

# O primeiro dígito do código IBGE da UF identifica a região.
REGIOES = {
    1: "Norte",
    2: "Nordeste",
    3: "Sudeste",
    4: "Sul",
    5: "Centro-Oeste",
}

REGIAO_POR_UF = {sigla: REGIOES[cod // 10] for sigla, (cod, _) in UFS.items()}

TOTAL_UFS = 27
