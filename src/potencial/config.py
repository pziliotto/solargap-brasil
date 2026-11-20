"""
PROJETO: SolarGap Brasil
ARQUIVO: potencial/config.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 19/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Premissas e caminhos da etapa TP4.5 — Potencial solar municipal. Assim como
    o esquema.py da preparação, este módulo NÃO contém lógica: centraliza os
    números que sustentam o cálculo do potencial técnico para que cada premissa
    seja declarada, justificada e alterada em um único lugar.

POTENCIAL TÉCNICO (etapas seguintes):
    geração anual (kWh) = irradiação (kWh/m²/dia) x 365 x área útil (m²)
                          x eficiência do painel x PR

OBS.:
    As premissas são simplificações deliberadas para comparação ENTRE
    municípios: o mesmo telhado típico é aplicado a todos, e a variação vem da
    irradiação e do número de domicílios. Não é um dimensionamento de projeto.
"""

from __future__ import annotations

from src.data_acquisition.coletor_base import obter_project_root

# ═══════════════════ Premissas técnicas ═══════════════════

# Performance Ratio: fração da energia teórica que chega à rede depois das perdas
# do sistema (temperatura, sujeira, cabeamento, inversor, sombreamento). Valores
# de 0,70 a 0,85 são usuais em sistemas residenciais; 0,75 é conservador.
PR = 0.75

# Eficiência de conversão do módulo fotovoltaico (STC). Módulos monocristalinos
# comerciais recentes ficam entre 0,20 e 0,23; 0,20 é o piso conservador.
EFICIENCIA_PAINEL = 0.20

# Área de telhado útil para módulos por domicílio (m²): descontadas águas mal
# orientadas, caixa d'água, sombreamento e afastamentos. Valor central da análise.
AREA_UTIL_TELHADO_M2 = 15

# Cenários de sensibilidade da área útil (m²). O valor central acima deve estar
# na lista, para que a análise de sensibilidade inclua o caso base.
AREAS_SENSIBILIDADE_M2 = [10, 15, 20]

# Potência de pico por m² de módulo (kWp/m²). Na condição padrão de teste (STC)
# a irradiância é 1 kW/m², logo 1 m² com eficiência de 20% ≈ 0,2 kWp.
IRRADIANCIA_STC_KW_M2 = 1.0
KWP_POR_M2 = EFICIENCIA_PAINEL * IRRADIANCIA_STC_KW_M2

# Anos usados como base da irradiação observada. A média de três anos suaviza a
# variabilidade interanual (nebulosidade, El Niño/La Niña).
ANOS_BASE = (2023, 2024, 2025)

# ═══════════════════ Malha municipal ═══════════════════

# Ano da malha do IBGE (via geobr), alinhado ao Censo 2022 usado no projeto.
ANO_MALHA = 2022
TOTAL_MUNICIPIOS = 5570

# ═══════════════════ NASA POWER ═══════════════════

# Resolução efetiva dos parâmetros solares no POWER (Release 9): grade global de
# 1° x 1°, origem CERES SYN1deg Ed. 4.2 (2001 até ~4 meses antes do presente) e
# CERES FLASHFlux 4A no período mais recente.
# Fonte: https://power.larc.nasa.gov/docs/methodology/data/sources_fluxes/
# As bordas das células ficam em graus inteiros e os centros em x,5 — conferido
# empiricamente em 19/11/2026 (pontos em -22,05 e -22,95 devolvem a mesma série;
# -21,95 devolve outra; um ponto exatamente em -22,0 cai na célula [-22, -21]).
RESOLUCAO_GRAUS_POWER = 1.0

# Faixa plausível de irradiação global horizontal média anual no Brasil
# (kWh/m²/dia). Fora dela, o valor indica erro de coleta ou de encaixe na grade.
FAIXA_PLAUSIVEL_KWH_M2_DIA = (3.5, 6.5)

# ═══════════════════ MMGD: recorte da métrica principal ═══════════════════

# Geração estimada "y" compara-se ao potencial de telhados residenciais "x". Só
# entra o que de fato está no telhado do próprio domicílio:
#   - classes Residencial e Rural (casas rurais costumam ser classe Rural);
#   - modalidade "Geração na própria UC". Autoconsumo remoto e geração
#     compartilhada costumam ser usinas instaladas num município que abastecem
#     consumidores de outros — somá-las inflaria y onde a usina está.
# Os valores são os textos de DscClasseConsumo / DscModalidadeHabilitado na base
# ANEEL (conferidos na base de referência 10/2026).
CLASSES_PRINCIPAIS = ("Residencial", "Rural")
MODALIDADE_PRINCIPAL = "Geracao na propria UC"

# Nome curto de cada modalidade da base, usado nas colunas kwp_mod_<nome>.
# "Condomínio" é o empreendimento com múltiplas unidades consumidoras (EMUC).
MODALIDADES_ANEEL = {
    "Geracao na propria UC": "propria_uc",
    "Auto consumo remoto": "autoconsumo_remoto",
    "Compartilhada": "compartilhada",
    "Condomínio": "multiplas_ucs",
}

# Municípios criados depois do Censo 2022 aparecem na ANEEL mas não na malha nem
# nos domicílios de 2022. A MMGD deles é reatribuída ao município de origem, onde
# os moradores foram recenseados — mantém o total nacional e a coerência x/y.
#   5101837 Boa Esperança do Norte (MT), instalado em 2025 a partir do distrito
#   de Boa Esperança, em Sorriso (5107925). Na base 10/2026: 34 unidades, 471,7 kW.
MUNICIPIOS_POSTERIORES_2022 = {"5101837": "5107925"}

# Tolerância da conferência do kWp nacional contra o total já reportado.
TOLERANCIA_TOTAL_KWP = 0.01

# ═══════════════════ Caminhos ═══════════════════

PROJECT_ROOT = obter_project_root(__file__)
PASTA_RAW_POWER = PROJECT_ROOT / "data" / "raw" / "nasa_power"
PASTA_INTERIM_POTENCIAL = PROJECT_ROOT / "data" / "interim" / "potencial"
PASTA_PROCESSED = PROJECT_ROOT / "data" / "processed"
PASTA_LOGS = PROJECT_ROOT / "logs"

ARQUIVO_PONTOS = PASTA_INTERIM_POTENCIAL / "municipios_pontos.parquet"
ARQUIVO_IRRADIACAO = PASTA_INTERIM_POTENCIAL / "irradiacao_municipal.parquet"
ARQUIVO_MMGD_MUNICIPAL = PASTA_INTERIM_POTENCIAL / "mmgd_municipal.parquet"

ARQUIVO_GOLD_MUNICIPAL = PASTA_PROCESSED / "potencial_municipal.parquet"
ARQUIVO_GOLD_MUNICIPAL_CSV = PASTA_PROCESSED / "potencial_municipal.csv"
ARQUIVO_GOLD_UF = PASTA_PROCESSED / "potencial_uf.parquet"
