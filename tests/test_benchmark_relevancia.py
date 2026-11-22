"""Benchmark v2 da relevância: divisão, estratégias, escolha, bootstrap e trava do teste."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.ia import benchmark_relevancia as b
from src.ia.benchmark_relevancia import ESTRATEGIAS

# SHA-256 do teste congelado em 22/11/2026 (etapa "dividir"). Se este teste
# falhar, o arquivo foi alterado: restaure-o do Git, nunca atualize o hash.
SHA256_TESTE_CONGELADO = (
    "3233b8176ad38bb377f5a2f9ac8d04379b2d1cb04fc987fc4b942627612e8577"
)


def test_teste_congelado_nao_mudou():
    assert b.sha256(b.ARQUIVO_TESTE) == SHA256_TESTE_CONGELADO


def test_congelar_recusa_sobrescrever():
    with pytest.raises(SystemExit):
        b.congelar(pd.DataFrame())


def test_divisao_versionada_e_disjunta_e_sem_ids_fora_v2():
    dev, teste = b.ler_conjunto(b.ARQUIVO_DEV), b.ler_conjunto(b.ARQUIVO_TESTE)
    assert len(dev) == 59 and len(teste) == 89
    assert not set(dev["id"]) & set(teste["id"])
    assert not (set(dev["id"]) | set(teste["id"])) & b.rotulagem.IDS_FORA_V2


def gabarito_sintetico(n: int = 100) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": [f"n{i:03d}" for i in range(n)],
            "relevante": ["sim" if i % 3 else "nao" for i in range(n)],
            "fonte": ["A" if i % 4 else "B" for i in range(n)],
            "gd_sem_solar": [i % 5 == 0 for i in range(n)],
        }
    )


def test_dividir_estratificado_exato_e_reprodutivel():
    g = gabarito_sintetico()
    dev, teste = b.dividir(g)
    assert len(dev) == 40 and len(teste) == 60
    for coluna in ("relevante", "fonte", "gd_sem_solar"):
        proporcao = dev[coluna].value_counts(normalize=True)
        assert (proporcao - g[coluna].value_counts(normalize=True)).abs().max() < 0.05
    dev2, _ = b.dividir(g.sample(frac=1, random_state=7))
    assert sorted(dev2["id"]) == sorted(dev["id"])


def base_sintetica() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "relevante": ["sim", "sim", "nao", "nao"],
            "fonte": ["A", "A", "B", "B"],
            "gd_sem_solar": [False, True, True, False],
            "p_atual": [0.9, 0.1, 0.2, 0.6],
            "p_ampla": [0.9, 0.7, 0.2, 0.1],
            "p_gd": [0.1, 0.8, 0.1, 0.1],
            "p_lei": [0.1, 0.1, 0.9, 0.1],
            "gd_no_titulo": [False, True, False, False],
            "gd_no_texto": [False, True, True, False],
        }
    )


def test_estrategias():
    base = base_sintetica()
    assert ESTRATEGIAS["atual"].prever(base, 0.5).tolist() == [
        "sim",
        "nao",
        "nao",
        "sim",
    ]
    assert ESTRATEGIAS["curtas"].prever(base, 0.5).tolist() == [
        "sim",
        "sim",
        "sim",
        "sim",
    ]
    assert ESTRATEGIAS["hibrido_titulo"].prever(base, 0.7).tolist() == [
        "sim",
        "sim",
        "nao",
        "nao",
    ]
    assert ESTRATEGIAS["hibrido_texto"].prever(base, 0.7).tolist()[2] == "sim"


def test_prf_classe_sim():
    v = pd.Series(["sim", "sim", "nao", "nao"])
    p = pd.Series(["sim", "nao", "sim", "nao"])
    assert b.prf(v, p) == {"n": 4, "precisao": 0.5, "recall": 0.5, "f1": 0.5}
    assert b.prf(v, pd.Series(["nao"] * 4))["f1"] == 0.0


def test_escolher_desempata_por_gd_e_custo():
    linhas = []
    for estrategia, f1_geral, f1_gd in (
        ("atual", 0.80, 0.0),
        ("curtas", 0.803, 0.7),  # empata com "ampla" no geral; vence no GD
        ("ampla", 0.804, 0.5),
    ):
        for limiar in (0.4, 0.5):
            linhas += [
                {
                    "estrategia": estrategia,
                    "limiar": limiar,
                    "recorte": "geral",
                    "f1": f1_geral,
                },
                {
                    "estrategia": estrategia,
                    "limiar": limiar,
                    "recorte": "gd_sem_solar",
                    "f1": f1_gd,
                },
            ]
    escolha = b.escolher(pd.DataFrame(linhas))
    assert (escolha["estrategia"], escolha["limiar"]) == ("curtas", 0.5)


def test_bootstrap_ic_contem_estimativa_e_diferenca_pareada():
    verdade = pd.Series(["sim"] * 30 + ["nao"] * 10)
    boa = verdade.copy()
    ruim = pd.Series(["sim"] * 40)
    r = b.bootstrap(
        verdade, {"boa": boa, "ruim": ruim}, [("boa", "ruim")], reamostragens=200
    )
    assert r["boa"]["f1"] == 1.0 and r["boa"]["ic95_f1"] == [1.0, 1.0]
    baixo, alto = r["ruim"]["ic95_f1"]
    assert baixo <= r["ruim"]["f1"] <= alto
    assert r["boa_menos_ruim"]["ic95"][0] > 0


class ModeloFalso:
    def avaliar_hipotese(self, texto, hipotese, limiar):
        return type(
            "R", (), {"probabilidade": 0.9 if "solar" in texto.lower() else 0.1}
        )()

    def classificar(self, texto, hipoteses):
        return type("R", (), {"rotulo": "favoravel"})()


def test_etapa_teste_roda_uma_vez(monkeypatch, tmp_path):
    """Ensaio com o conjunto de DESENVOLVIMENTO no lugar do teste e modelo falso."""
    monkeypatch.setattr(b, "ARQUIVO_TESTE", b.ARQUIVO_DEV)
    monkeypatch.setattr(b, "ARQUIVO_TESTE_RESULTADO", tmp_path / "r.json")
    monkeypatch.setattr(b, "ARQUIVO_TESTE_SAIDAS", tmp_path / "s.csv")
    escolha = tmp_path / "e.json"
    escolha.write_text(
        json.dumps({"estrategia": "curtas", "limiar": 0.5}), encoding="utf-8"
    )
    monkeypatch.setattr(b, "ARQUIVO_ESCOLHA", escolha)
    monkeypatch.setattr(b, "carregar_modelo", lambda dispositivo=None: ModeloFalso())

    resultado = b.etapa_teste()
    assert set(resultado["relevancia"]) == {"geral", "gd_sem_solar", "por_fonte"}
    assert "ic95_f1" in resultado["relevancia"]["gd_sem_solar"]["escolhida"]
    assert resultado["tom"]["teste"]["linha_base"]["classe"] == "favoravel"
    assert len(pd.read_csv(tmp_path / "s.csv", sep=";")) == 59
    with pytest.raises(SystemExit):  # segunda execução recusada
        b.etapa_teste()


# ── Correção de métrica: F1 macro (segunda escolha) ──


def test_metricas_duas_classes_e_f1_macro():
    v = pd.Series(["sim", "sim", "sim", "nao"])
    m = b.metricas_duas_classes(v, pd.Series(["sim"] * 4))
    assert m["recall_sim"] == 1.0 and m["f1_nao"] == 0.0
    assert m["f1_macro"] == pytest.approx((6 / 7) / 2)
    assert b._f1_macro(
        v.to_numpy(), pd.Series(["sim"] * 4).to_numpy()
    ) == pytest.approx(m["f1_macro"])


def test_escolher_macro_aplica_restricoes_e_desempate():
    linhas = [
        {
            "estrategia": "sempre_sim",
            "limiar": None,
            "f1_macro": 0.42,
            "precisao_sim": 0.7,
            "f1_sim_gd_sem_solar": 0.7,
        },
        {
            "estrategia": "atual",
            "limiar": 0.5,
            "f1_macro": 0.80,
            "precisao_sim": 0.9,
            "f1_sim_gd_sem_solar": 0.0,
        },
        {
            "estrategia": "curtas",
            "limiar": 0.5,
            "f1_macro": 0.40,
            "precisao_sim": 0.7,
            "f1_sim_gd_sem_solar": 0.7,
        },
        {
            "estrategia": "ampla",
            "limiar": 0.5,
            "f1_macro": 0.702,
            "precisao_sim": 0.80,
            "f1_sim_gd_sem_solar": 0.5,
        },
        {
            "estrategia": "hibrido_titulo",
            "limiar": 0.4,
            "f1_macro": 0.700,
            "precisao_sim": 0.89,
            "f1_sim_gd_sem_solar": 0.6,
        },
    ]
    escolha = b.escolher_macro(pd.DataFrame(linhas))
    # "atual" sai pela restrição de GD; "curtas" não passa de "sempre sim";
    # "ampla" e "hibrido_titulo" empatam (< 0,005) e vence a maior precisão.
    assert (escolha["estrategia"], escolha["limiar"]) == ("hibrido_titulo", 0.4)


def test_bootstrap_macro_diferenca_pareada():
    verdade = pd.Series(["sim"] * 30 + ["nao"] * 10)
    r = b.bootstrap_macro(
        verdade,
        {"boa": verdade.copy(), "trivial": pd.Series(["sim"] * 40)},
        [("boa", "trivial")],
        200,
    )
    assert r["boa"]["f1_macro"] == 1.0 and r["trivial"]["f1_macro"] < 0.5
    assert r["boa_menos_trivial"]["ic95"][0] > 0


def test_segunda_consulta_nao_sobrescreve_a_primeira(monkeypatch, tmp_path):
    primeira = b.ARQUIVO_TESTE_RESULTADO
    assert primeira.exists()  # a primeira consulta fica guardada como está
    monkeypatch.setattr(b, "ARQUIVO_TESTE_RESULTADO_V2", primeira)  # simula v2 já feita
    with pytest.raises(SystemExit):
        b.etapa_teste_v2()
