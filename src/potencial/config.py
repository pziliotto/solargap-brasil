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

# ═══════════════════ Caminhos ═══════════════════

PROJECT_ROOT = obter_project_root(__file__)
PASTA_RAW_POWER = PROJECT_ROOT / "data" / "raw" / "nasa_power"
PASTA_INTERIM_POTENCIAL = PROJECT_ROOT / "data" / "interim" / "potencial"
PASTA_LOGS = PROJECT_ROOT / "logs"

ARQUIVO_PONTOS = PASTA_INTERIM_POTENCIAL / "municipios_pontos.parquet"
ARQUIVO_IRRADIACAO = PASTA_INTERIM_POTENCIAL / "irradiacao_municipal.parquet"
