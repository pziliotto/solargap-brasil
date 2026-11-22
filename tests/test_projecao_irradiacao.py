"""Método delta da projeção da irradiação (Tarefa 6), com arrays sintéticos e sem rede."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data_acquisition import coletor_cmip6 as cmip6
from src.potencial import projecao_irradiacao as proj
from src.potencial.potencial_municipal import energia_mwh_ano

# ── delta relativo e ensemble ──


def test_delta_relativo_por_celula():
    historico = np.array([[200.0, 250.0], [np.nan, 0.0]])
    futuro = np.array([[210.0, 240.0], [220.0, 5.0]])
    delta = proj.delta_relativo(historico, futuro)
    assert delta[0, 0] == pytest.approx(0.05)
    assert delta[0, 1] == pytest.approx(-0.04)
    assert np.isnan(delta[1, 0])  # histórico ausente (mar)
    assert np.isnan(delta[1, 1])  # histórico zero: sem divisão


def test_media_temporal_ignora_dias_ausentes_e_mantem_mar_nan():
    diario = np.array(
        [[[100.0, np.nan]], [[300.0, np.nan]], [[np.nan, np.nan]]]
    )  # 3 dias, 1 x 2 células
    media = proj.media_temporal(diario)
    assert media[0, 0] == pytest.approx(200.0) and np.isnan(media[0, 1])


def test_metodo_delta_completo_em_grade_sintetica():
    """Climatologia histórica 1995–2014 x futura, como no pipeline real."""
    rng = np.random.default_rng(0)
    base = rng.uniform(150, 250, size=(4, 4))
    anos_hist = np.stack(
        [base * (1 + rng.normal(0, 0.01, base.shape)) for _ in range(20)]
    )
    anos_fut = np.stack([base * 1.03 for _ in range(10)])
    delta = proj.delta_relativo(
        proj.media_temporal(anos_hist), proj.media_temporal(anos_fut)
    )
    assert np.allclose(delta, 0.03, atol=0.005)


def test_resumo_ensemble_mediana_e_faixa():
    deltas = np.array(
        [[0.01, -0.02], [0.03, 0.00], [0.02, -0.01], [-0.01, 0.01], [0.05, 0.02]]
    )
    resumo = proj.resumo_ensemble(deltas)
    assert resumo["mediano"].tolist() == pytest.approx([0.02, 0.00])
    assert resumo["min"].tolist() == pytest.approx([-0.01, -0.02])
    assert resumo["max"].tolist() == pytest.approx([0.05, 0.02])


# ── associação município -> célula ──


def test_celula_mais_proxima_pula_celula_sem_dado():
    lat = np.array([-10.125, -9.875])
    lon = np.array([-40.125, -39.875])
    valido = np.array([[True, False], [True, True]])  # (-10.125, -39.875) é mar
    i, j, distancia = proj.celula_mais_proxima(
        np.array([-10.12, -9.88]), np.array([-39.88, -40.12]), lat, lon, valido
    )
    # 1º ponto está sobre a célula sem dado: vai para a vizinha válida mais próxima
    assert (i[0], j[0]) in {(0, 0), (1, 1)}
    assert distancia[0] == pytest.approx(27.3, abs=1.0)
    assert (i[1], j[1]) == (1, 0) and distancia[1] < 1


def test_lon_180():
    assert proj.lon_180(np.array([286.125, 326.125, 10.0])).tolist() == [
        -73.875,
        -33.875,
        10.0,
    ]


# ── projeção de x, y e gap ──


def base_sintetica() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cod_ibge": ["1", "2"],
            "uf": ["BA", "BA"],
            "irradiacao_kwh_m2_dia": [5.0, 6.0],
            "kwp_potencial": [1000.0, 500.0],
            "kwp_local_res_rural": [100.0, 600.0],  # município 2 com y > x
            "kwp_local_res_rural_aneel": [120.0, 650.0],
        }
    )


def deltas_sinteticos() -> pd.DataFrame:
    linhas = []
    for cod in ("1", "2"):
        for modelo, delta in zip("ABCDE", (0.01, 0.03, 0.02, -0.01, 0.05)):
            linhas.append(
                {
                    "cod_ibge": cod,
                    "cenario": "ssp245",
                    "janela": "2030-2039",
                    "modelo": modelo,
                    "delta": delta,
                }
            )
    return pd.DataFrame(linhas)


def test_projetar_so_muda_a_irradiacao_e_taxa_constante():
    tabela = proj.projetar(base_sintetica(), deltas_sinteticos())
    linha = tabela[(tabela["cod_ibge"] == "1") & (tabela["modelo"] == "B")].iloc[0]
    assert linha["H_projetada"] == pytest.approx(5.0 * 1.03)
    assert linha["x_projetado_mwh_ano"] == pytest.approx(energia_mwh_ano(1000.0, 5.15))
    assert linha["gap_projetado_mwh_ano"] == pytest.approx(
        energia_mwh_ano(1000.0, 5.15) - energia_mwh_ano(100.0, 5.15)
    )
    taxa = tabela["y_projetado_mwh_ano"] / tabela["x_projetado_mwh_ano"]
    taxa_atual = tabela["kwp_local_res_rural"] / tabela["kwp_potencial"]
    assert np.allclose(taxa, taxa_atual)  # H se cancela


def test_resumo_entre_modelos_e_gap_negativo():
    tabela = proj.projetar(base_sintetica(), deltas_sinteticos())
    resumo = proj.resumir_modelos(tabela, ["cod_ibge", "cenario", "janela"]).set_index(
        "cod_ibge"
    )
    um = resumo.loc["1"]
    assert (um["delta_mediano"], um["delta_min"], um["delta_max"]) == pytest.approx(
        (0.02, -0.01, 0.05)
    )
    assert um["x_projetado_mwh_ano"] == pytest.approx(
        energia_mwh_ano(1000.0, 5.0 * 1.02)
    )
    assert (
        um["x_projetado_min_mwh_ano"]
        < um["x_projetado_mwh_ano"]
        < um["x_projetado_max_mwh_ano"]
    )
    dois = resumo.loc["2"]  # gap negativo: o mínimo vem do modelo de MAIOR delta
    assert dois["gap_projetado_min_mwh_ano"] == pytest.approx(
        energia_mwh_ano(500.0 - 600.0, 6.0 * 1.05)
    )
    assert dois["n_modelos"] == 5


def test_alertas_de_sanidade():
    deltas = pd.DataFrame({"delta": [0.02, -0.11, 0.105, 0.099]})
    assert proj.alertas_sanidade(deltas, 0.10)["delta"].tolist() == [-0.11, 0.105]


# ── coletor (sem rede) ──


def test_pedidos_e_url_de_recorte():
    lista = cmip6.pedidos()
    assert len(lista) == 5 * (20 + 21 + 21)
    url = cmip6.url_recorte(cmip6.Pedido("GFDL-ESM4", "ssp585", 2045))
    assert (
        "GFDL-ESM4/ssp585/r1i1p1f1/rsds/rsds_day_GFDL-ESM4_ssp585_r1i1p1f1_gr1_2045_v2.0.nc"
        in url
    )
    assert "north=6&south=-34&west=-74&east=-34" in url and "accept=netcdf4" in url


def test_arquivo_invalido_nao_entra_no_cache(tmp_path):
    truncado = tmp_path / "truncado.nc"
    truncado.write_bytes(b"\x89HDF\r\n\x1a\n" + b"\x00" * 100)
    assert not cmip6.arquivo_valido(truncado)


def test_gold_municipal_e_uf_de_ponta_a_ponta():
    lat = np.array([-10.125, -9.875])
    lon = np.array([-40.125, -39.875])
    deltas = {}
    for modelo, d in zip("ABCDE", (0.01, 0.03, 0.02, -0.01, 0.05)):
        for janela in ("2030-2039", "2040-2050"):
            grade = np.full((2, 2), d)
            grade[0, 1] = np.nan  # célula de mar
            deltas[(modelo, "ssp245", janela)] = grade
    pontos = pd.DataFrame(
        {"cod_ibge": ["1", "2"], "lat": [-10.12, -9.88], "lon": [-39.88, -40.12]}
    )
    base = base_sintetica()
    base["x_mwh_ano"] = energia_mwh_ano(
        base["kwp_potencial"], base["irradiacao_kwh_m2_dia"]
    )
    base["y_mwh_ano"] = energia_mwh_ano(
        base["kwp_local_res_rural"], base["irradiacao_kwh_m2_dia"]
    )
    base["y_aneel_mwh_ano"] = energia_mwh_ano(
        base["kwp_local_res_rural_aneel"], base["irradiacao_kwh_m2_dia"]
    )
    base["gap_mwh_ano"] = base["x_mwh_ano"] - base["y_mwh_ano"]
    base["taxa_realizacao"] = base["y_mwh_ano"] / base["x_mwh_ano"]
    base["taxa_realizacao_aneel"] = base["y_aneel_mwh_ano"] / base["x_mwh_ano"]

    deltas_mun = proj.tabela_deltas_municipais(pontos, lat, lon, deltas)
    assert deltas_mun["delta"].notna().all()  # o ponto sobre o mar usou a vizinha
    municipal = proj.montar_municipal(base, deltas_mun)
    assert len(municipal) == 2 * 2  # municípios x janelas
    assert {
        "delta_mediano",
        "delta_min",
        "delta_max",
        "H_projetada",
        "x_projetado_mwh_ano",
        "gap_projetado_mwh_ano",
    } <= set(municipal.columns)
    assert municipal["delta_mediano"].tolist() == pytest.approx([0.02] * 4)

    uf = proj.montar_uf(base, deltas_mun)
    assert len(uf) == 2 and uf["n_modelos"].eq(5).all()
    # Delta igual em todos os municípios: o delta da UF é o mesmo
    assert uf["delta_mediano"].tolist() == pytest.approx([0.02, 0.02])
    assert uf["x_projetado_mwh_ano"].iloc[0] == pytest.approx(
        base["x_mwh_ano"].sum() * 1.02
    )
    assert uf["taxa_realizacao"].iloc[0] == pytest.approx(
        base["y_mwh_ano"].sum() / base["x_mwh_ano"].sum()
    )
