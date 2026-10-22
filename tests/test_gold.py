"""construir_gold com uma Silver sintética: agregação conferida e sem coluna de ICMS."""

import pandas as pd

from src.preparacao import construir_gold, esquema


def test_gold_com_silver_sintetica(tmp_path, monkeypatch):
    linhas = []
    for sigla in esquema.UFS:
        linhas += [
            {
                "sigla_uf": sigla,
                "ano": 2022,
                "classe_consumo": "Residencial",
                "fonte_imputada": False,
                "potencia_kw": 10.0,
                "fonte_geracao": esquema.FONTE_SOLAR,
            },
            {
                "sigla_uf": sigla,
                "ano": 2023,
                "classe_consumo": None,
                "fonte_imputada": sigla == "MA",
                "potencia_kw": 5.0,
                "fonte_geracao": esquema.FONTE_SOLAR,
            },
            {
                "sigla_uf": sigla,
                "ano": 2023,
                "classe_consumo": "Rural",
                "fonte_imputada": False,
                "potencia_kw": 99.0,
                "fonte_geracao": "Hídrica",
            },  # fora do escopo solar
        ]
    silver = tmp_path / "mmgd_silver.parquet"
    pd.DataFrame(linhas).to_parquet(silver)
    populacao = tmp_path / "populacao_uf_silver.csv"
    pd.DataFrame(
        [{"cod_uf": cod, "populacao": 1_000} for cod, _ in esquema.UFS.values()]
    ).to_csv(populacao, sep=";", index=False)

    monkeypatch.setattr(construir_gold, "SILVER_MMGD", silver)
    monkeypatch.setattr(construir_gold, "SILVER_POP_UF", populacao)
    monkeypatch.setattr(construir_gold, "PASTA_PROCESSED", tmp_path)
    monkeypatch.setattr(construir_gold, "SAIDA_AGREGADO", tmp_path / "agregado.csv")
    monkeypatch.setattr(construir_gold, "SAIDA_UF", tmp_path / "uf.csv")
    monkeypatch.setattr(construir_gold, "PASTA_LOGS", tmp_path / "logs")

    construir_gold.construir_gold()

    agregado = pd.read_csv(tmp_path / "agregado.csv", sep=";")
    uf = pd.read_csv(tmp_path / "uf.csv", sep=";")
    assert (
        agregado["qtd_empreendimentos"].sum() == 2 * esquema.TOTAL_UFS
    )  # hídrica excluída
    assert (agregado["classe_consumo"] == "Não informada").sum() == esquema.TOTAL_UFS
    assert len(uf) == esquema.TOTAL_UFS
    assert (
        uf.set_index("sigla_uf").loc["SP", "watts_por_habitante"] == 15.0
    )  # 15 kW = 15.000 W / 1.000 hab.
    assert uf.set_index("sigla_uf").loc["MA", "pct_imputados"] == 50.0
    assert not any("icms" in coluna for coluna in uf.columns)
