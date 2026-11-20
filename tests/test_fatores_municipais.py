"""
Testes da tabela de fatores municipais (TP4.5, Tarefa 3): leitura do SIDRA,
tarifa ponderada pelos dias, ligação distribuidora -> município com filtro de
adjacência, cooperativas, MapBiomas e as junções da Gold (cod_ibge com 7
dígitos, sem duplicatas, 5.570 linhas, nenhuma variável derivada da MMGD).

Dados sintéticos pequenos; o último teste confere a Gold real, se existir.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.potencial import config, fatores

# ═══════════════════ SIDRA ═══════════════════


def _gravar_sidra(tmp_path, nome, legenda_extra, registros):
    legenda = {
        "NC": "Nível Territorial (Código)",
        "V": "Valor",
        "D1C": "Município (Código)",
        "D2C": "Ano (Código)",
        "D3C": "Variável (Código)",
        **legenda_extra,
    }
    caminho = tmp_path / nome
    caminho.write_text(json.dumps([legenda] + registros), encoding="utf-8")
    return caminho


def test_ler_sidra_flat_converte_valores_especiais_em_ausente(tmp_path):
    caminho = _gravar_sidra(
        tmp_path,
        "renda.json",
        {},
        [
            {
                "NC": "6",
                "V": "1200.50",
                "D1C": "3500001",
                "D2C": "2022",
                "D3C": "13431",
            },
            {"NC": "6", "V": "...", "D1C": "3500002", "D2C": "2022", "D3C": "13431"},
            {"NC": "6", "V": "900", "D1C": "3500001", "D2C": "2022", "D3C": "13534"},
        ],
    )
    tabela = fatores.renda(caminho).set_index("cod_ibge")
    assert tabela.loc["3500001", "renda_domiciliar_pc_media"] == pytest.approx(1200.5)
    assert tabela.loc["3500001", "renda_domiciliar_pc_mediana"] == pytest.approx(900)
    assert np.isnan(tabela.loc["3500002", "renda_domiciliar_pc_media"])


def test_urbanizacao_e_razao_urbana_sobre_total(tmp_path):
    registros = [
        {"NC": "6", "V": v, "D1C": "3500001", "D2C": "2022", "D3C": "93", "D4C": c}
        for c, v in (("6795", "1000"), ("1", "750"), ("2", "250"))
    ]
    caminho = _gravar_sidra(
        tmp_path, "urb.json", {"D4C": "Situação do domicílio (Código)"}, registros
    )
    tabela = fatores.urbanizacao(caminho)
    assert tabela.loc[0, "pct_populacao_urbana"] == pytest.approx(75.0)


def test_populacao_area_densidade_e_log(tmp_path):
    registros = [
        {"NC": "6", "V": v, "D1C": "3500001", "D2C": "2022", "D3C": var}
        for var, v in (("93", "1000"), ("6318", "50.5"), ("614", "19.8"))
    ]
    caminho = _gravar_sidra(tmp_path, "area.json", {}, registros)
    linha = fatores.populacao_area_densidade(caminho).iloc[0]
    assert linha["populacao_2022"] == 1000
    assert linha["area_km2"] == pytest.approx(50.5)
    assert linha["densidade_hab_km2"] == pytest.approx(19.8)
    assert linha["log_populacao"] == pytest.approx(np.log(1000))


# ═══════════════════ Tarifa ═══════════════════


def _tarifa(cnpj, sig, inicio, fim, te, tusd, **extra):
    linha = {
        "DscSubGrupo": "B1",
        "DscModalidadeTarifaria": "Convencional",
        "DscClasse": "Residencial",
        "DscSubClasse": "Residencial",
        "DscDetalhe": "Não se aplica",
        "DscBaseTarifaria": "Tarifa de Aplicação",
        "DscUnidadeTerciaria": "MWh",
        "NumCNPJDistribuidora": cnpj,
        "SigAgente": sig,
        "DatInicioVigencia": inicio,
        "DatFimVigencia": fim,
        "VlrTE": te,
        "VlrTUSD": tusd,
    }
    linha.update(extra)
    return linha


def test_tarifa_ponderada_pelos_dias_dentro_da_janela():
    tarifas = pd.DataFrame(
        [
            # começa antes da janela: só conta a partir de 2023-01-01
            _tarifa(1, "D1", "2022-07-01", "2023-06-30", 200, 300),  # 500, 181 dias
            _tarifa(1, "D1", "2023-07-01", "2025-12-31", 300, 400),  # 700, 915 dias
            # fora da janela: ignorada
            _tarifa(1, "D1", "2026-01-01", "2026-12-31", 900, 900),
            # outras linhas do arquivo não entram
            _tarifa(
                1, "D1", "2023-01-01", "2025-12-31", 1, 1, DscSubClasse="Baixa Renda"
            ),
            _tarifa(1, "D1", "2023-01-01", "2025-12-31", 1, 1, DscDetalhe="SCEE"),
            _tarifa(
                1,
                "D1",
                "2023-01-01",
                "2025-12-31",
                1,
                1,
                DscBaseTarifaria="Base Econômica",
            ),
        ]
    )
    resultado = fatores.tarifa_b1_por_distribuidora(tarifas).iloc[0]
    assert resultado["cnpj"] == "00000000000001"
    assert resultado["dias_cobertos"] == 181 + 915
    assert resultado["dias_janela"] == 1096
    assert resultado["tarifa_b1_rs_mwh"] == pytest.approx(
        (500 * 181 + 700 * 915) / 1096
    )


# ═══════════════════ Distribuidora -> município ═══════════════════


def _dec_fec():
    return pd.DataFrame(
        {
            "SigAgente": ["EPB   ", "EPB", "EQTL MA", "COOP", "ANTIGA"],
            "NumCNPJ": [10, 10, 20, 30, 40],
            "IdeConjUndConsumidoras": [1, 2, 3, 4, 5],
            "AnoIndice": [2024, 2024, 2025, 2023, 2021],
        }
    )


def _indqual():
    # PB = 25, MA = 21, CE = 23; conjunto 5 só existe antes de 2023
    linhas = [
        (1, "2500001"),
        (1, "2500002"),
        (2, "2500003"),  # EPB na PB (principal)
        (2, "2300001"),  # EPB no CE: vizinha da PB, mantém
        (2, "2100001"),  # EPB no MA: não vizinha, descarta
        (3, "2100001"),
        (3, "2100002"),  # distribuidora do MA
        (4, "2500001"),  # cooperativa também na PB: município com 2 distribuidoras
        (5, "2500004"),  # conjunto antigo: fora
    ]
    return pd.DataFrame(
        {
            "IdeConjUnidConsumidoras": [str(c) for c, _ in linhas],
            "CodMunicipio": [m for _, m in linhas],
            "SigUF": [None] * len(linhas),  # lacunas como no arquivo real
        }
    )


def _pares():
    conjuntos = fatores.conjuntos_atuais(_dec_fec(), ano_minimo=2023)
    return fatores.filtrar_adjacencia(
        fatores.ligar_distribuidoras(_indqual(), conjuntos)
    )


def test_conjuntos_atuais_e_sigla_sem_espacos():
    conjuntos = fatores.conjuntos_atuais(_dec_fec(), ano_minimo=2023)
    assert set(conjuntos["conjunto"]) == {1, 2, 3, 4}
    assert set(conjuntos["sig_agente"]) == {"EPB", "EQTL MA", "COOP"}
    assert conjuntos["cnpj"].str.len().eq(14).all()


def test_ligacao_usa_uf_do_codigo_ibge_e_remove_duplicatas():
    pares = _pares()
    assert not pares.duplicated(["cod_ibge", "cnpj"]).any()
    uf = dict(zip(pares["cod_ibge"], pares["uf"]))
    assert uf["2500001"] == "PB" and uf["2100001"] == "MA" and uf["2300001"] == "CE"
    assert "2500004" not in set(pares["cod_ibge"])  # conjunto anterior a 2023


def test_adjacencia_descarta_par_geograficamente_impossivel():
    pares = _pares().set_index(["cod_ibge", "sig_agente"])
    assert pares.loc[("2100001", "EPB"), "descartado_adjacencia"]
    assert not pares.loc[
        ("2300001", "EPB"), "descartado_adjacencia"
    ]  # CE vizinho da PB
    assert pares.loc[("2100001", "EPB"), "uf_principal"] == "PB"
    assert not pares.loc[("2100001", "EQTL MA"), "descartado_adjacencia"]


def test_vizinhanca_entre_ufs_e_simetrica():
    for uf, vizinhas in config.UFS_VIZINHAS.items():
        for outra in vizinhas:
            assert uf in config.UFS_VIZINHAS[outra], (uf, outra)
    assert len(config.UFS_VIZINHAS) == 27


def test_cooperativa_pela_classificacao_mais_recente():
    iasc = pd.DataFrame(
        {
            "NumCNPJ": ["30", "30", "10"],
            "NumAno": ["2022", "2025", "2025"],
            "DscClassificacao": ["Concessionária", "Permissionária", "Concessionária"],
        }
    )
    cooperativas = fatores.classificar_cooperativas(iasc)
    assert cooperativas["00000000000030"]
    assert not cooperativas["00000000000010"]


def test_fatores_distribuidora_media_simples_e_flags():
    tarifas = pd.DataFrame(
        {
            "cnpj": ["00000000000010", "00000000000020", "00000000000030"],
            "tarifa_b1_rs_mwh": [700.0, 800.0, 1000.0],
        }
    )
    cooperativas = pd.Series({"00000000000030": True, "00000000000010": False})
    resultado = fatores.fatores_distribuidora(
        _pares(), tarifas, cooperativas
    ).set_index("cod_ibge")
    # 2500001: EPB (700) + cooperativa (1000) -> média simples
    assert resultado.loc["2500001", "tarifa_b1_rs_mwh"] == pytest.approx(850)
    assert resultado.loc["2500001", "multi_distribuidora"]
    assert resultado.loc["2500001", "cooperativa"]
    assert resultado.loc["2500001", "distribuidoras"] == "COOP;EPB"
    # 2100001: o par EPB foi descartado, fica só a distribuidora do MA
    assert resultado.loc["2100001", "n_distribuidoras"] == 1
    assert resultado.loc["2100001", "tarifa_b1_rs_mwh"] == pytest.approx(800)
    assert not resultado.loc["2100001", "multi_distribuidora"]


# ═══════════════════ MapBiomas e PIB ═══════════════════


def test_mapbiomas_soma_os_biomas_do_municipio():
    cobertura = pd.DataFrame(
        {
            "geocode": ["3500001", "3500001", "3500001", "350002"],
            "class_level_1": ["3. Farming", "1. Forest", "3. Farming", "1. Forest"],
            "y2023": [30.0, 50.0, 20.0, 10.0],
        }
    )
    tabela = fatores.pct_area_agropecuaria(cobertura, "y2023").set_index("cod_ibge")
    assert tabela.loc["3500001", "pct_area_agropecuaria"] == pytest.approx(50.0)
    assert tabela.loc["0350002", "pct_area_agropecuaria"] == 0  # zfill e sem agro


def test_participacao_agro_no_vab():
    pib = pd.DataFrame(
        {
            "cod_ibge": ["3500001"],
            "vab_agropecuaria_mil": [25.0],
            "vab_total_mil": [100.0],
        }
    )
    assert fatores.participacao_agro(pib).loc[
        0, "pct_vab_agropecuaria"
    ] == pytest.approx(25)


# ═══════════════════ Junções da Gold ═══════════════════


def _base(n=3):
    return pd.DataFrame(
        {
            "cod_ibge": [f"{3500001 + i}" for i in range(n)],
            "nome": [f"M{i}" for i in range(n)],
            "uf": ["SP"] * n,
        }
    )


def test_montar_fatores_left_join_sem_imputar():
    renda = pd.DataFrame(
        {"cod_ibge": ["3500001"], "renda_domiciliar_pc_media": [1000.0]}
    )
    icms = pd.DataFrame(
        {"uf": ["SP"], "icms_ano_inicio_isencao": [2015], "icms_meses_isencao": [131]}
    )
    tabela = fatores.montar_fatores(_base(), [renda, icms])
    assert len(tabela) == 3
    assert (
        tabela["renda_domiciliar_pc_media"].isna().sum() == 2
    )  # ausente, não imputado
    assert (tabela["icms_meses_isencao"] == 131).all()  # junção por UF
    assert (tabela["regiao"] == "Sudeste").all()


def test_montar_fatores_recusa_chave_duplicada():
    duplicada = pd.DataFrame(
        {"cod_ibge": ["3500001", "3500001"], "renda_domiciliar_pc_media": [1.0, 2.0]}
    )
    with pytest.raises(ValueError, match="duplicada"):
        fatores.montar_fatores(_base(), [duplicada])


def test_validar_fatores_aponta_problemas_de_chave():
    tabela = pd.concat([_base(), _base(1)], ignore_index=True)
    tabela.loc[1, "cod_ibge"] = "350001"
    problemas = " | ".join(fatores.validar_fatores(tabela))
    assert "linhas" in problemas
    assert "duplicado" in problemas
    assert "7 dígitos" in problemas


def test_relatorio_de_ausentes():
    tabela = fatores.montar_fatores(
        _base(4),
        [pd.DataFrame({"cod_ibge": ["3500001"], "renda_domiciliar_pc_media": [1.0]})],
    )
    relatorio = fatores.relatorio_ausentes(tabela).set_index("variavel")
    assert relatorio.loc["renda_domiciliar_pc_media", "n_ausentes"] == 3
    assert relatorio.loc["renda_domiciliar_pc_media", "pct_ausentes"] == 75.0


# ═══════════════════ Gold real ═══════════════════


@pytest.mark.skipif(
    not config.ARQUIVO_GOLD_FATORES.exists(),
    reason="fatores_municipais.parquet não gerado",
)
def test_gold_real_tem_5570_municipios_unicos_e_nenhuma_variavel_da_mmgd():
    gold = pd.read_parquet(config.ARQUIVO_GOLD_FATORES)
    assert len(gold) == config.TOTAL_MUNICIPIOS
    assert gold["cod_ibge"].str.fullmatch(r"\d{7}").all()
    assert not gold["cod_ibge"].duplicated().any()
    assert list(gold.columns) == fatores.COLUNAS_GOLD
    proibidas = ("kwp", "mmgd", "potencia", "taxa_realizacao", "y_", "x_", "gap")
    assert not [c for c in gold.columns if c.startswith(proibidas)]
    # Referência versionada (data/processed), para o teste rodar num clone limpo;
    # data/interim/ não é versionado.
    potencial = pd.read_parquet(config.ARQUIVO_GOLD_MUNICIPAL, columns=["cod_ibge"])
    assert set(gold["cod_ibge"]) == set(potencial["cod_ibge"])
