"""
Testes do tratamento da potência suspeita (registros de 75 kW): diagnóstico
por distribuidora, sinalização, imputação hierárquica com fallbacks, limite
conservador e escolha da visão na camada de serviços.

Dados sintéticos pequenos; os nomes de distribuidora são fictícios, para
garantir que nenhuma regra depende de "PR" ou "COPEL".
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.preparacao import esquema, potencia_suspeita
from src.servicos import indicadores


def _empreendimentos(distribuidora, classe, n, n_75, kw_normal=5.0, uf="XX"):
    potencias = [75.0] * n_75 + [kw_normal] * (n - n_75)
    return pd.DataFrame(
        {
            "distribuidora": distribuidora,
            "classe_consumo": classe,
            "potencia_kw": potencias,
            "sigla_uf": uf,
            "cod_municipio": 1_000_001,
            "ano": 2022,
        }
    )


def _base_diagnostico():
    normais = [0, 1, 2, 1, 0, 2, 1, 1, 2]  # 0% a 2% de residências com 75 kW
    partes = [
        _empreendimentos(f"D{i}", "Residencial", 100, k) for i, k in enumerate(normais)
    ]
    partes += [
        # fora do padrão: 30% das residências com 75 kW
        _empreendimentos("ALVO", "Residencial", 100, 30),
        # amostra pequena: 1 em 6 (17%), mas sem evidência estatística
        _empreendimentos("PEQUENA", "Residencial", 6, 1),
        # cooperativa rural: muitos 75 kW legítimos fora da classe Residencial
        _empreendimentos("RURAL", "Residencial", 100, 0),
        _empreendimentos("RURAL", "Rural", 100, 100),
    ]
    return pd.concat(partes, ignore_index=True)


# ═══════════════════ Diagnóstico ═══════════════════


def test_wilson_limite_inferior():
    # 30/100: intervalo de Wilson 95% ≈ [0,219; 0,396]
    assert potencia_suspeita.limite_inferior_wilson(30, 100) == pytest.approx(
        0.2189, abs=1e-3
    )
    # zero sucessos: limite inferior zero
    assert potencia_suspeita.limite_inferior_wilson(0, 50) == pytest.approx(0.0)
    assert np.isnan(potencia_suspeita.limite_inferior_wilson(0, 0))


def test_diagnostico_sinaliza_so_a_distribuidora_fora_do_padrao():
    tabela, referencias = potencia_suspeita.diagnosticar_distribuidoras(
        _base_diagnostico()
    )
    sinalizadas = set(tabela.loc[tabela["sinalizada"], "distribuidora"])
    assert sinalizadas == {"ALVO"}

    por_nome = tabela.set_index("distribuidora")
    # amostra pequena: fração alta, mas o limite inferior de Wilson fica abaixo
    assert por_nome.loc["PEQUENA", "fracao_classe"] > referencias["limite"]
    assert por_nome.loc["PEQUENA", "wilson_inferior"] < referencias["limite"]
    # cooperativa rural: 50% dos registros em 75 kW, mas nenhum residencial
    assert (
        por_nome.loc["RURAL", "n_valor_total"] / por_nome.loc["RURAL", "n_total"] == 0.5
    )
    assert por_nome.loc["RURAL", "fracao_classe"] == 0
    assert not por_nome.loc["RURAL", "sinalizada"]


def test_diagnostico_usa_mediana_e_mad_entre_distribuidoras():
    tabela, referencias = potencia_suspeita.diagnosticar_distribuidoras(
        _base_diagnostico()
    )
    fracoes = tabela["fracao_classe"]
    mediana = fracoes.median()
    mad = (fracoes - mediana).abs().median()
    assert referencias["mediana"] == pytest.approx(mediana)
    assert referencias["mad"] == pytest.approx(mad)
    assert referencias["limite"] == pytest.approx(mediana + esquema.FATOR_MAD * mad)


def test_sem_distribuidora_fora_do_padrao_nada_e_sinalizado():
    base = _base_diagnostico()
    base = base[base["distribuidora"] != "ALVO"]
    tabela, _ = potencia_suspeita.diagnosticar_distribuidoras(base)
    assert not tabela["sinalizada"].any()


# ═══════════════════ Sinalização ═══════════════════


def test_sinaliza_todos_os_75_kw_exatos_da_distribuidora_em_qualquer_classe():
    registros = pd.DataFrame(
        {
            "distribuidora": ["ALVO", "ALVO", "ALVO", "ALVO", "OUTRA"],
            "classe_consumo": [
                "Residencial",
                "Comercial",
                "Residencial",
                "Rural",
                "Residencial",
            ],
            "potencia_kw": [75.0, 75.0, 74.9, 5.0, 75.0],
        }
    )
    flag = potencia_suspeita.sinalizar(registros, {"ALVO"})
    assert flag.tolist() == [True, True, False, False, False]


# ═══════════════════ Imputação ═══════════════════


def _base_imputacao():
    """Referências (não sinalizadas) e alvos (sinalizados) para cada nível."""
    linhas = [
        # (municipio, distribuidora, uf, classe, ano, kW, sinalizado)
        # nível 1: município M1 + Residencial + 2020 tem [4, 6] -> 5
        (1, "D", "AA", "Residencial", 2020, 4.0, False),
        (1, "D", "AA", "Residencial", 2020, 6.0, False),
        (1, "D", "AA", "Residencial", 2019, 8.0, False),
        (1, "D", "AA", "Residencial", 2020, 75.0, True),
        # nível 2: M1 + Residencial sem 2021 -> mediana de [4, 6, 8] = 6
        (1, "D", "AA", "Residencial", 2021, 75.0, True),
        # nível 3: M2 sem referência Rural; distribuidora D + Rural + 2020 em M3: [10, 20] -> 15
        (3, "D", "AA", "Rural", 2020, 10.0, False),
        (3, "D", "AA", "Rural", 2020, 20.0, False),
        (2, "D", "AA", "Rural", 2020, 75.0, True),
        # nível 4: distribuidora E sem referência; UF AA + Comercial: [30, 50] -> 40
        (4, "F", "AA", "Comercial", 2015, 30.0, False),
        (5, "F", "AA", "Comercial", 2016, 50.0, False),
        (6, "E", "AA", "Comercial", 2018, 75.0, True),
        # mínimo de amostra: M7 tem só 1 referência Industrial (3 kW) -> não vale;
        # sem outro nível disponível, fica sem imputação
        (7, "G", "BB", "Industrial", 2020, 3.0, False),
        (7, "G", "BB", "Industrial", 2020, 75.0, True),
        # classe ausente é tratada como "Não informada"
        (8, "H", "CC", None, 2020, 2.0, False),
        (8, "H", "CC", None, 2020, 2.0, False),
        (8, "H", "CC", None, 2020, 75.0, True),
    ]
    df = pd.DataFrame(
        linhas,
        columns=[
            "cod_municipio",
            "distribuidora",
            "sigla_uf",
            "classe_consumo",
            "ano",
            "potencia_kw",
            "sinalizado",
        ],
    )
    return df.drop(columns="sinalizado"), df["sinalizado"]


def test_imputacao_percorre_a_hierarquia_e_registra_o_nivel():
    registros, flag = _base_imputacao()
    corrigida, nivel = potencia_suspeita.imputar_potencia(registros, flag, minimo=2)

    esperado = {
        3: (5.0, "municipio_classe_ano"),
        4: (6.0, "municipio_classe"),
        7: (15.0, "distribuidora_classe_ano"),
        10: (40.0, "uf_classe"),
        12: (75.0, "sem_imputacao"),
        15: (2.0, "municipio_classe_ano"),
    }
    for indice, (kw, nome) in esperado.items():
        assert corrigida[indice] == pytest.approx(kw), indice
        assert nivel[indice] == nome, indice


def test_registros_nao_sinalizados_ficam_intactos_e_sem_nivel():
    registros, flag = _base_imputacao()
    corrigida, nivel = potencia_suspeita.imputar_potencia(registros, flag, minimo=2)
    assert (corrigida[~flag] == registros.loc[~flag, "potencia_kw"]).all()
    assert nivel[~flag].isna().all()
    assert len(corrigida) == len(registros)  # nenhum registro excluído


def test_minimo_de_amostra_empurra_para_o_nivel_seguinte():
    registros, flag = _base_imputacao()
    # com mínimo 3, o nível 1 de M1 (2 referências) não vale; M1 + Residencial tem 3
    corrigida, nivel = potencia_suspeita.imputar_potencia(registros, flag, minimo=3)
    assert nivel[3] == "municipio_classe"
    assert corrigida[3] == pytest.approx(6.0)


def test_sinalizado_nunca_serve_de_referencia():
    registros, flag = _base_imputacao()
    # se os 75 kW entrassem na mediana de M1 + Residencial + 2020 ([4, 6, 75]), daria 6
    corrigida, _ = potencia_suspeita.imputar_potencia(registros, flag, minimo=2)
    assert corrigida[3] == pytest.approx(5.0)


# ═══════════════════ Aplicação completa ═══════════════════


def test_aplicar_tratamento_e_limite_conservador():
    base = _base_diagnostico()
    # referências para a imputação: ALVO também tem residências e comércios normais
    base = pd.concat(
        [base, _empreendimentos("ALVO", "Comercial", 20, 5, kw_normal=12.0)],
        ignore_index=True,
    )
    tratada, diagnostico = potencia_suspeita.aplicar_tratamento(base)

    assert len(tratada) == len(base)
    assert set(diagnostico.loc[diagnostico["sinalizada"], "distribuidora"]) == {"ALVO"}
    sinal = tratada["flag_potencia_suspeita"]
    assert sinal.sum() == 30 + 5  # todos os 75 kW da ALVO, residenciais e comerciais
    assert (tratada.loc[sinal, "potencia_kw"] == 75).all()  # dado oficial preservado

    res = sinal & (tratada["classe_consumo"] == "Residencial")
    com = sinal & (tratada["classe_consumo"] == "Comercial")
    # residências corrigidas para a mediana das residências do mesmo município
    assert (tratada.loc[res, "potencia_corrigida_kw"] == 5.0).all()
    assert (tratada.loc[com, "potencia_corrigida_kw"] == 12.0).all()
    # conservador: só residenciais corrigidos
    assert (tratada.loc[res, "potencia_conservadora_kw"] == 5.0).all()
    assert (tratada.loc[com, "potencia_conservadora_kw"] == 75.0).all()
    assert (
        tratada.loc[~sinal, ["potencia_corrigida_kw", "potencia_conservadora_kw"]]
        .eq(tratada.loc[~sinal, "potencia_kw"], axis=0)
        .all()
        .all()
    )


# ═══════════════════ Visão na camada de serviços ═══════════════════


def _agregado():
    return pd.DataFrame(
        {
            "sigla_uf": ["PR", "PR", "MA"],
            "ano": [2021, 2021, 2021],
            "classe_consumo": ["Residencial", "Residencial", "Residencial"],
            "fonte_imputada": [False, True, False],
            "potencia_kw": [750.0, 10.0, 100.0],
            "potencia_corrigida_kw": [60.0, 10.0, 100.0],
            "potencia_conservadora_kw": [60.0, 10.0, 100.0],
            "qtd_empreendimentos": [10, 2, 20],
            "qtd_potencia_suspeita": [10, 0, 0],
        }
    )


def test_visao_corrigida_usa_potencia_corrigida_e_aneel_a_oficial():
    classes = ("Residencial",)
    corrigida = indicadores.filtrar(_agregado(), 2012, 2026, classes, True)
    aneel = indicadores.filtrar(_agregado(), 2012, 2026, classes, False)
    assert corrigida["potencia_kw"].sum() == pytest.approx(60 + 10 + 100)
    assert aneel["potencia_kw"].sum() == pytest.approx(750 + 100)  # sem imputados


def test_gold_sem_colunas_novas_continua_funcionando():
    antigo = _agregado().drop(
        columns=[
            "potencia_corrigida_kw",
            "potencia_conservadora_kw",
            "qtd_potencia_suspeita",
        ]
    )
    filtrado = indicadores.filtrar(antigo, 2012, 2026, ("Residencial",), True)
    assert filtrado["potencia_kw"].sum() == pytest.approx(860)
    assert indicadores.potencia_suspeita(antigo, 2012, 2026, ("Residencial",)) == {
        "registros": 0,
        "kw_oficial": 0.0,
        "kw_corrigido": 0.0,
    }


def test_resumo_da_potencia_suspeita_para_o_aviso():
    resumo = indicadores.potencia_suspeita(_agregado(), 2012, 2026, ("Residencial",))
    assert resumo["registros"] == 10
    assert resumo["kw_oficial"] == pytest.approx(850)
    assert resumo["kw_corrigido"] == pytest.approx(160)
