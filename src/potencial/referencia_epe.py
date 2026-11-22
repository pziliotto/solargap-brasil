"""
PROJETO: SolarGap Brasil
ARQUIVO: potencial/referencia_epe.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 19/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Potencial técnico fotovoltaico residencial por UF segundo a EPE, usado só
    como referência externa de ordem de grandeza para o x do projeto.

FONTE:
    EPE — Empresa de Pesquisa Energética. Nota Técnica DEA 19/14, "Inserção da
    Geração Fotovoltaica Distribuída no Brasil – Condicionantes e Impactos".
    Série Recursos Energéticos. Rio de Janeiro, outubro de 2014.
    Tabela 1 — Potencial Técnico Fotovoltaico Residencial (p. 21), coluna
    "Potencial Fotovoltaico Residencial (GWh/ano)". Dados de EPE/GIZ (Lange, 2012).
    https://www.epe.gov.br/sites-pt/publicacoes-dados-abertos/publicacoes/PublicacoesArquivos/publicacao-251/topico-311/DEA%2019%20-%20%20Inser%C3%A7%C3%A3o%20da%20Gera%C3%A7%C3%A3o%20Fotovoltaica%20Distribu%C3%ADda%20no%20Brasil%20-%20Condicionantes%20e%20Impactos%20VF%20%20(Revisada)[1].pdf

PREMISSAS DA EPE (p. 15–17), diferentes das nossas:
    - domicílios do Censo 2010 por setor censitário (casas e apartamentos);
    - telhado médio de 85 m² por casa e 15 m² por apartamento (Ghisi, 2006),
      com fator de aproveitamento de 30% (≈ 25,5 m² úteis por casa);
    - irradiação global no plano inclinado (INPE);
    - eficiência global de 12% (módulo x Performance Ratio).
    O projeto usa Censo 2022, 15 m² úteis por domicílio, irradiação horizontal
    (NASA POWER 2023–2025) e 20% x 0,75 = 15% de eficiência global. A comparação
    é de ordem de grandeza, não de validação ponto a ponto.

OBS.:
    Valores transcritos manualmente da Tabela 1. A soma das 27 UFs confere com
    o total impresso (287.505 GWh/ano) — teste em tests/test_potencial_municipal.py.
"""

from __future__ import annotations

FONTE_EPE = (
    "EPE, Nota Técnica DEA 19/14 — Inserção da Geração Fotovoltaica Distribuída "
    "no Brasil: Condicionantes e Impactos (out/2014), Tabela 1"
)
ANO_EPE = 2014

# Total Brasil impresso na Tabela 1 (GWh/ano)
TOTAL_BRASIL_GWH_ANO = 287_505

# UF -> potencial técnico fotovoltaico residencial (GWh/ano)
POTENCIAL_EPE_GWH_ANO = {
    "SP": 62_196,
    "MG": 32_193,
    "RJ": 23_521,
    "BA": 20_674,
    "RS": 17_257,
    "PR": 17_170,
    "CE": 12_527,
    "PE": 12_352,
    "GO": 10_687,
    "SC": 9_417,
    "MA": 8_935,
    "PA": 8_935,
    "PB": 5_738,
    "ES": 5_212,
    "MT": 4_993,
    "RN": 4_862,
    "PI": 4_862,
    "MS": 4_424,
    "AL": 4_424,
    "AM": 3_679,
    "DF": 3_592,
    "SE": 3_066,
    "RO": 2_321,
    "TO": 2_234,
    "AC": 964,
    "AP": 701,
    "RR": 569,
}
