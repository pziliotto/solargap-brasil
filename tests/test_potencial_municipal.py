"""
Testes do potencial técnico municipal (TP4.5, Tarefa 2): fórmulas de x e y,
recorte de classe/modalidade da MMGD, reatribuição de municípios novos,
agregação por UF e leitura dos domicílios do SIDRA.

Tudo com dados sintéticos pequenos — nenhum teste lê a base ANEEL nem acessa
a rede.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.data_acquisition import ibge_domicilios
from src.potencial import config, mmgd_municipal, potencial_municipal, referencia_epe
from src.potencial.potencial_municipal import coluna_sensibilidade

FATOR = config.PR * 365 / 1000  # MWh/ano por (kWp x kWh/m²/dia)


# ═══════════════════ Fórmulas ═══════════════════


def test_kwp_potencial_um_m2_com_20_por_cento_vale_0_2_kwp():
    assert config.KWP_POR_M2 == pytest.approx(0.2)
    assert potencial_municipal.kwp_potencial(1, area_m2=1) == pytest.approx(0.2)
    assert potencial_municipal.kwp_potencial(100) == pytest.approx(100 * 15 * 0.2)


def test_energia_anual():
    # 300 kWp x 5 kWh/m²/dia x 0,75 x 365 / 1000 = 410,625 MWh/ano
    assert potencial_municipal.energia_mwh_ano(300, 5.0) == pytest.approx(410.625)


# ═══════════════════ Recorte de classe e modalidade ═══════════════════


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("Residencial", "residencial"),
        ("Poder Público", "poder_publico"),
        ("Iluminação pública", "iluminacao_publica"),
        (None, "nao_informada"),
        (np.nan, "nao_informada"),
    ],
)
def test_normalizar_rotulo(texto, esperado):
    assert mmgd_municipal.normalizar_rotulo(texto) == esperado


def test_rotulo_modalidade_usa_nomes_curtos():
    assert mmgd_municipal.rotulo_modalidade("Geracao na propria UC") == "propria_uc"
    assert (
        mmgd_municipal.rotulo_modalidade("Auto consumo remoto") == "autoconsumo_remoto"
    )
    assert mmgd_municipal.rotulo_modalidade("Condomínio") == "multiplas_ucs"
    assert mmgd_municipal.rotulo_modalidade(None) == "nao_informada"


def _registros():
    """Empreendimentos sintéticos de dois municípios."""
    return (
        pd.DataFrame(
            [
                # município A: só residencial local e rural local entram na métrica
                ("3500001", "SP", "Residencial", "Geracao na propria UC", 5.0),
                ("3500001", "SP", "Residencial", "Geracao na propria UC", 7.0),
                ("3500001", "SP", "Rural", "Geracao na propria UC", 20.0),
                ("3500001", "SP", "Residencial", "Auto consumo remoto", 75.0),
                ("3500001", "SP", "Residencial", "Compartilhada", 1000.0),
                ("3500001", "SP", "Comercial", "Geracao na propria UC", 30.0),
                ("3500001", "SP", "Rural", "Condomínio", 40.0),
                # município B: nada entra na métrica principal
                ("3500002", "SP", "Industrial", "Geracao na propria UC", 300.0),
                ("3500002", "SP", None, None, 2.0),
            ],
            columns=[
                "cod_municipio",
                "sigla_uf",
                "classe_consumo",
                "modalidade",
                "potencia_kw",
            ],
        )
        .astype({"cod_municipio": "Int64"})
        .assign(
            # sem correções: as três visões coincidem
            fonte_imputada=False,
            flag_potencia_suspeita=False,
            potencia_corrigida_kw=lambda df: df["potencia_kw"],
            potencia_conservadora_kw=lambda df: df["potencia_kw"],
        )
    )


def test_tres_visoes_de_potencia_por_municipio():
    registros = _registros()
    # Residencial local de 75 kW suspeito, corrigido para 6 kW nas visões
    # corrigida e conservadora; rural local de 75 kW suspeito, corrigido só na
    # corrigida; um registro de fonte imputada, fora do critério ANEEL.
    extra = pd.DataFrame(
        [
            (
                "3500001",
                "SP",
                "Residencial",
                "Geracao na propria UC",
                75.0,
                False,
                True,
                6.0,
                6.0,
            ),
            (
                "3500001",
                "SP",
                "Rural",
                "Geracao na propria UC",
                75.0,
                False,
                True,
                10.0,
                75.0,
            ),
            (
                "3500001",
                "SP",
                "Residencial",
                "Geracao na propria UC",
                4.0,
                True,
                False,
                4.0,
                4.0,
            ),
        ],
        columns=[
            "cod_municipio",
            "sigla_uf",
            "classe_consumo",
            "modalidade",
            "potencia_kw",
            "fonte_imputada",
            "flag_potencia_suspeita",
            "potencia_corrigida_kw",
            "potencia_conservadora_kw",
        ],
    ).astype({"cod_municipio": "Int64"})
    tabela = mmgd_municipal.consolidar(
        mmgd_municipal.resumir_registros(
            pd.concat([registros, extra], ignore_index=True)
        )
    )
    a = tabela.set_index("cod_ibge").loc["3500001"]
    base_local = 5 + 7 + 20
    assert a["kwp_local_res_rural"] == pytest.approx(base_local + 6 + 10 + 4)
    assert a["kwp_local_res_rural_conservadora"] == pytest.approx(
        base_local + 6 + 75 + 4
    )
    assert a["kwp_local_res_rural_aneel"] == pytest.approx(base_local + 75 + 75)
    assert a["n_potencia_suspeita"] == 2
    assert a["n_local_res_rural"] == 6


def test_metrica_principal_so_residencial_e_rural_na_propria_uc():
    tabela = mmgd_municipal.consolidar(mmgd_municipal.resumir_registros(_registros()))
    a = tabela.set_index("cod_ibge").loc["3500001"]
    assert a["kwp_local_res_rural"] == pytest.approx(5 + 7 + 20)
    assert a["n_local_res_rural"] == 3
    assert a["kwp_total"] == pytest.approx(5 + 7 + 20 + 75 + 1000 + 30 + 40)
    assert a["n_unidades"] == 7

    b = tabela.set_index("cod_ibge").loc["3500002"]
    assert b["kwp_local_res_rural"] == 0
    assert b["n_local_res_rural"] == 0


def test_colunas_por_classe_e_modalidade_somam_o_total():
    tabela = mmgd_municipal.consolidar(mmgd_municipal.resumir_registros(_registros()))
    classes = tabela.filter(like="kwp_classe_").sum(axis=1)
    modalidades = tabela.filter(like="kwp_mod_").sum(axis=1)
    assert np.allclose(classes, tabela["kwp_total"])
    assert np.allclose(modalidades, tabela["kwp_total"])

    a = tabela.set_index("cod_ibge").loc["3500001"]
    assert a["kwp_mod_autoconsumo_remoto"] == 75
    assert a["kwp_mod_compartilhada"] == 1000
    assert a["kwp_mod_multiplas_ucs"] == 40
    assert a["kwp_classe_residencial"] == pytest.approx(5 + 7 + 75 + 1000)
    b = tabela.set_index("cod_ibge").loc["3500002"]
    assert b["kwp_classe_nao_informada"] == 2
    assert b["kwp_mod_nao_informada"] == 2


def test_consolidar_soma_partes_de_chunks_diferentes():
    registros = _registros()
    partes = [
        mmgd_municipal.resumir_registros(registros.iloc[:4]),
        mmgd_municipal.resumir_registros(registros.iloc[4:]),
    ]
    em_partes = mmgd_municipal.consolidar(pd.concat(partes, ignore_index=True))
    inteiro = mmgd_municipal.consolidar(mmgd_municipal.resumir_registros(registros))
    pd.testing.assert_frame_equal(em_partes, inteiro)


# ═══════════════════ Gold municipal ═══════════════════


def _entradas():
    pontos = pd.DataFrame(
        {
            "cod_ibge": ["2900001", "4300001", "4300002"],
            "nome": ["Sol", "Nuvem", "Sem MMGD"],
            "uf": ["BA", "RS", "RS"],
        }
    )
    irradiacao = pd.DataFrame(
        {
            "cod_ibge": ["2900001", "4300001", "4300002"],
            "irradiacao_kwh_m2_dia": [6.0, 4.0, 4.5],
        }
    )
    domicilios = pd.DataFrame(
        {"cod_ibge": ["2900001", "4300001", "4300002"], "domicilios": [1000, 1000, 10]}
    )
    mmgd = pd.DataFrame(
        {
            "cod_ibge": ["2900001", "4300001"],
            "uf": ["BA", "RS"],
            "kwp_total": [900.0, 5000.0],
            "n_unidades": [100, 400],
            "kwp_local_res_rural": [300.0, 3300.0],
            "n_local_res_rural": [60, 350],
            "kwp_mod_propria_uc": [500.0, 4000.0],
            # visões de comparação: ANEEL maior (75 kW oficiais), conservadora no meio
            "kwp_total_aneel": [900.0, 6500.0],
            "kwp_total_conservadora": [900.0, 5600.0],
            "kwp_local_res_rural_aneel": [300.0, 4800.0],
            "kwp_local_res_rural_conservadora": [300.0, 3900.0],
            "n_potencia_suspeita": [0, 20],
        }
    )
    return pontos, irradiacao, domicilios, mmgd


def test_gold_calcula_y_e_taxa_nas_tres_visoes():
    gold = potencial_municipal.montar_gold(*_entradas()).set_index("cod_ibge")
    nuvem = gold.loc["4300001"]  # 3.000 kWp potencial
    assert nuvem["taxa_realizacao"] == pytest.approx(3300 / 3000)
    assert nuvem["taxa_realizacao_aneel"] == pytest.approx(4800 / 3000)
    assert nuvem["taxa_realizacao_conservador"] == pytest.approx(3900 / 3000)
    assert nuvem["y_aneel_mwh_ano"] == pytest.approx(4800 * 4.0 * FATOR)
    assert nuvem["y_total_aneel_mwh_ano"] == pytest.approx(6500 * 4.0 * FATOR)
    assert bool(nuvem["flag_taxa_acima_1_aneel"]) is True
    # o gap e a flag principais seguem a visão corrigida
    assert nuvem["gap_mwh_ano"] == pytest.approx(
        nuvem["x_mwh_ano"] - nuvem["y_mwh_ano"]
    )

    uf = potencial_municipal.agregar_uf(potencial_municipal.montar_gold(*_entradas()))
    rs = uf.set_index("uf").loc["RS"]
    assert rs["n_potencia_suspeita"] == 20
    assert rs["taxa_realizacao_aneel"] == pytest.approx(
        rs["y_aneel_mwh_ano"] / rs["x_mwh_ano"]
    )
    assert rs["n_municipios_taxa_acima_1_aneel"] == 1


def test_gold_aplica_as_formulas():
    gold = potencial_municipal.montar_gold(*_entradas()).set_index("cod_ibge")
    sol = gold.loc["2900001"]
    assert sol["kwp_potencial"] == pytest.approx(1000 * 15 * 0.2)  # 3.000 kWp
    assert sol["x_mwh_ano"] == pytest.approx(3000 * 6.0 * FATOR)
    assert sol["y_mwh_ano"] == pytest.approx(300 * 6.0 * FATOR)
    assert sol["y_total_mwh_ano"] == pytest.approx(900 * 6.0 * FATOR)
    assert sol["gap_mwh_ano"] == pytest.approx(sol["x_mwh_ano"] - sol["y_mwh_ano"])
    assert sol["taxa_realizacao"] == pytest.approx(0.1)
    assert sol["regiao"] == "Nordeste"


def test_irradiacao_se_cancela_na_taxa_mas_nao_no_gap():
    pontos, irradiacao, domicilios, mmgd = _entradas()
    mmgd.loc[1, "kwp_local_res_rural"] = 300.0  # mesmos kWp e domicílios que "Sol"
    gold = potencial_municipal.montar_gold(pontos, irradiacao, domicilios, mmgd)
    sol, nuvem = gold.set_index("cod_ibge").loc[["2900001", "4300001"]].itertuples()
    assert sol.taxa_realizacao == pytest.approx(nuvem.taxa_realizacao)
    assert sol.gap_mwh_ano / nuvem.gap_mwh_ano == pytest.approx(6.0 / 4.0)


def test_municipio_sem_mmgd_tem_y_zero_e_taxa_acima_de_1_e_marcada():
    gold = potencial_municipal.montar_gold(*_entradas()).set_index("cod_ibge")
    sem = gold.loc["4300002"]
    assert sem["kwp_total"] == 0 and sem["y_mwh_ano"] == 0 and sem["n_unidades"] == 0
    assert sem["gap_mwh_ano"] == pytest.approx(sem["x_mwh_ano"])

    nuvem = gold.loc["4300001"]  # 3.300 kWp local sobre 3.000 kWp potencial
    assert nuvem["taxa_realizacao"] == pytest.approx(1.1)
    assert bool(nuvem["flag_taxa_acima_1"]) is True
    assert not gold.loc["2900001", "flag_taxa_acima_1"]
    assert len(gold) == 3  # marcado, não descartado


def test_sensibilidade_da_area_e_proporcional():
    gold = potencial_municipal.montar_gold(*_entradas())
    base = gold["x_mwh_ano"]
    for area in config.AREAS_SENSIBILIDADE_M2:
        assert np.allclose(
            gold[coluna_sensibilidade(area)], base * area / config.AREA_UTIL_TELHADO_M2
        )
    assert np.allclose(gold[coluna_sensibilidade(config.AREA_UTIL_TELHADO_M2)], base)


def test_gold_falha_se_faltar_domicilio():
    pontos, irradiacao, domicilios, mmgd = _entradas()
    with pytest.raises(ValueError, match="sem irradiação ou domicílios"):
        potencial_municipal.montar_gold(pontos, irradiacao, domicilios.iloc[:2], mmgd)


def test_municipio_posterior_a_2022_e_reatribuido_a_origem():
    pontos, irradiacao, domicilios, mmgd = _entradas()
    novo = mmgd.iloc[[0]].assign(cod_ibge="9999999")
    mmgd = pd.concat([mmgd, novo], ignore_index=True)

    with pytest.raises(ValueError, match="fora da malha"):
        potencial_municipal.montar_gold(pontos, irradiacao, domicilios, mmgd)

    reatribuido = potencial_municipal.reatribuir_municipios_novos(
        mmgd, mapa={"9999999": "2900001"}
    ).set_index("cod_ibge")
    assert reatribuido.loc["2900001", "kwp_total"] == 1800
    assert reatribuido.loc["2900001", "n_unidades"] == 200
    assert reatribuido["kwp_total"].sum() == mmgd["kwp_total"].sum()


def test_mapa_de_municipios_novos_aponta_para_codigos_validos():
    for novo, origem in config.MUNICIPIOS_POSTERIORES_2022.items():
        assert len(novo) == len(origem) == 7
        assert novo[:2] == origem[:2]  # mesma UF


# ═══════════════════ Agregação por UF ═══════════════════


def test_taxa_da_uf_e_razao_das_somas_e_nao_media_das_taxas():
    gold = potencial_municipal.montar_gold(*_entradas())
    uf = potencial_municipal.agregar_uf(gold).set_index("uf")

    rs = gold[gold["uf"] == "RS"]
    assert uf.loc["RS", "x_mwh_ano"] == pytest.approx(rs["x_mwh_ano"].sum())
    assert uf.loc["RS", "gap_mwh_ano"] == pytest.approx(rs["gap_mwh_ano"].sum())
    esperado = rs["y_mwh_ano"].sum() / rs["x_mwh_ano"].sum()
    assert uf.loc["RS", "taxa_realizacao"] == pytest.approx(esperado)
    assert uf.loc["RS", "taxa_realizacao"] != pytest.approx(
        rs["taxa_realizacao"].mean()
    )
    assert uf.loc["RS", "n_municipios"] == 2
    assert uf.loc["RS", "n_municipios_taxa_acima_1"] == 1
    assert (
        uf.loc["BA", "x_epe_2014_gwh_ano"] == referencia_epe.POTENCIAL_EPE_GWH_ANO["BA"]
    )


# ═══════════════════ Validação ═══════════════════


def test_validacao_do_total_nacional_com_tolerancia_de_1_por_cento():
    gold = potencial_municipal.montar_gold(*_entradas())
    total = gold["kwp_total"].sum()
    problemas = potencial_municipal.validar_gold(gold, {"silver": total * 1.005})
    assert not any("kWp nacional" in p for p in problemas)
    problemas = potencial_municipal.validar_gold(gold, {"silver": total * 1.05})
    assert any("kWp nacional" in p for p in problemas)


def test_validacao_exige_tolerancia_contra_cada_referencia():
    gold = potencial_municipal.montar_gold(*_entradas())
    total = gold["kwp_total"].sum()
    problemas = potencial_municipal.validar_gold(
        gold, {"silver": total, "gold_uf.csv": total * 1.048}
    )
    sobre_total = [p for p in problemas if p.startswith("kWp nacional")]
    assert sobre_total == ["kWp nacional difere 4.58% de gold_uf.csv (limite 1%)"]


def test_tabela_epe_completa_e_soma_o_total_impresso():
    assert len(referencia_epe.POTENCIAL_EPE_GWH_ANO) == 27
    assert sum(referencia_epe.POTENCIAL_EPE_GWH_ANO.values()) == (
        referencia_epe.TOTAL_BRASIL_GWH_ANO
    )


# ═══════════════════ Domicílios (SIDRA) ═══════════════════


def _json_sidra(registros):
    legenda = {
        "NC": "Nível Territorial (Código)",
        "V": "Valor",
        "D1C": "Município (Código)",
        "D1N": "Município",
    }
    return [legenda] + [
        {"NC": "6", "V": valor, "D1C": codigo, "D1N": "X"}
        for codigo, valor in registros
    ]


def test_ler_domicilios_do_view_flat(tmp_path, monkeypatch):
    monkeypatch.setattr(ibge_domicilios, "TOTAL_MUNICIPIOS", 2)
    caminho = tmp_path / "dom.json"
    caminho.write_text(
        json.dumps(_json_sidra([("3500002", "250"), ("3500001", "1200")])),
        encoding="utf-8",
    )
    tabela = ibge_domicilios.ler_domicilios(caminho)
    assert tabela["cod_ibge"].tolist() == ["3500001", "3500002"]
    assert tabela["domicilios"].tolist() == [1200, 250]


def test_ler_domicilios_rejeita_valor_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr(ibge_domicilios, "TOTAL_MUNICIPIOS", 2)
    caminho = tmp_path / "dom.json"
    caminho.write_text(
        json.dumps(_json_sidra([("3500001", "1200"), ("3500002", "-")])),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sem valor"):
        ibge_domicilios.ler_domicilios(caminho)


def test_url_registra_tabela_e_variavel():
    assert "/agregados/4712/" in ibge_domicilios.URL_SIDRA
    assert "/variaveis/381" in ibge_domicilios.URL_SIDRA
    assert "N6[all]" in ibge_domicilios.URL_SIDRA
