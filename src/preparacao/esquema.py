"""
PROJETO: SolarGap Brasil
ARQUIVO: esquema.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/09/2026
ATUALIZAÇÃO: 21/10/2026 — TP3: contrato do corpus de notícias (colunas, níveis
             de texto e regra de identificação), remoção de import duplicado

DESCRIÇÃO:
    Constantes compartilhadas entre as camadas Silver e Gold e, a partir da etapa 2,
    pelos scrapers. Esse módulo NÃO contém lógica de tratamento: centraliza nomes de
    colunas, cortes temporais e o cadastro das UFs para que nenhum desses valores seja
    digitado à mão em mais de um arquivo.

OBS.:
    Se a ANEEL renomear uma coluna ou o cadastro de UFs precisar de ajuste a correção
    acontece só aqui.

OBS. TP3:
    O import de COLUNAS_SENSIVEIS vindo do aneel.py foi removido: a constante era
    importada e redefinida logo abaixo (o Ruff acusa F811). Além de redundante, o
    import fazia o esquema — e tudo que depende dele, como a API — carregar o
    coletor da ANEEL sem necessidade.

    A única função do módulo, id_noticia(), é exceção consciente à regra de "sem
    lógica": a identificação de uma notícia precisa ser idêntica em quem coleta
    (scrapers) e em quem recebe (API, POST /noticias). Duas cópias da regra
    divergiriam com o tempo e gerariam duplicatas no corpus.
"""

from __future__ import annotations

import hashlib

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

# Fonte única da lista de colunas com dado pessoal (LGPD). Os scripts do TP1
# (aneel.py, gerar_amostra.py) mantêm cópia própria por serem anteriores a este módulo.
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


# ═══════════════════ Corpus de notícias ═══════════════════

# Ordem e nomes das colunas do corpus (data/processed/corpus_noticias.csv).
# Contrato compartilhado por: scrapers (escrevem), API (lê e recebe POST),
# dashboard (lê) e, no TP4, o modelo de linguagem (preenche resumo/sentimento).
COLUNAS_CORPUS = [
    "id",
    "fonte",
    "url",
    "data_publicacao",
    "titulo",
    "linha_fina",
    "texto",
    "ufs_mencionadas",
    "nivel_texto",
    "tag_origem",
    "coletado_em",
    "resumo",
    "sentimento",
]

# integral  -> texto completo armazenado (fontes com licença que autoriza reprodução)
# metadados -> só título, linha fina, data e link (fontes sem autorização de cópia)
NIVEL_INTEGRAL = "integral"
NIVEL_METADADOS = "metadados"
NIVEIS_TEXTO = (NIVEL_INTEGRAL, NIVEL_METADADOS)

# Colunas que o modelo de linguagem preencherá no TP4. Uma nova coleta NUNCA
# pode apagar o que já foi preenchido nelas (ver mesclar_corpus no coletor).
COLUNAS_MODELO = ["resumo", "sentimento"]


def id_noticia(url: str) -> str:
    """Identificador estável de uma notícia: 12 primeiros caracteres do MD5 da URL.

    Mesma regra usada no TP2 — os ids do corpus já versionado continuam válidos.
    """
    return hashlib.md5(url.strip().encode("utf-8")).hexdigest()[:12]
