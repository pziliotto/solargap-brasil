"""
Pacote da etapa TP4.5 — Potencial solar municipal.

Compara o potencial técnico de geração solar em telhados de cada município com a
geração estimada da MMGD instalada, explica o gap com fatores socioeconômicos e
projeta a irradiação para 2030–2050.

Módulos:
    config.py           premissas técnicas e caminhos (sem lógica)
    malha_municipal.py  pontos representativos dos 5.570 municípios (geobr)
    irradiacao.py       Silver de irradiação média municipal (NASA POWER)

A coleta da NASA POWER mora em src/data_acquisition/coletor_nasa_power.py, junto
dos demais coletores.
"""
