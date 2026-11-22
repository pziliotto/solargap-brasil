"""Seleção da planilha de pendentes do benchmark v2 (dados sintéticos de teste)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.ia import rotulagem as r


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("A Lei 14.300 e a energia solar", "Lei 14.300"),
        ("a cobrança do fio B sobre a geração distribuída", "fio B"),
        ("microgeração e minigeração", "minigeração"),
        ("microgeradores residenciais", "microgeração"),
        ("a geração distribuída cresceu", "geração distribuída"),
        ("usina fotovoltaica flutuante", "fotovoltaica"),
        ("leilão de energia solar", "energia solar"),
        ("hidrelétrica no Tapajós", "outra"),
    ],
)
def test_palavra_chave_mais_especifica(texto, esperada):
    assert r.palavra_chave(texto) == esperada


def test_gd_sem_solar():
    assert r.gd_sem_solar(
        "ANEEL multa distribuidora por irregularidades na geração distribuída"
    )
    assert r.gd_sem_solar("Regras da Lei 14.300 para quem gera a própria energia")
    assert not r.gd_sem_solar("geração distribuída solar cresce")
    assert not r.gd_sem_solar("microgeração fotovoltaica")
    assert not r.gd_sem_solar("energia solar em escolas")  # não é termo de GD


def test_alocar_proporcional_com_minimo_um():
    tamanhos = pd.Series({"a": 80, "b": 15, "c": 4, "d": 1})
    cotas = r.alocar(tamanhos, 20)
    assert cotas.sum() == 20
    assert (cotas >= 1).all() and (cotas <= tamanhos).all()
    assert cotas["a"] > cotas["b"] > cotas["c"]


def test_alocar_pega_tudo_quando_falta():
    tamanhos = pd.Series({"a": 3, "b": 2})
    assert r.alocar(tamanhos, 10).to_dict() == {"a": 3, "b": 2}


def corpus_sintetico() -> pd.DataFrame:
    linhas = []
    for i in range(60):
        fonte = "Agência Brasil" if i % 3 else "Agência Gov"
        texto = [
            "energia solar em alta",
            "usina fotovoltaica",
            "geração distribuída cresce com painéis solares",
            "Lei 14.300 muda regras para quem gera a própria energia",
        ][i % 4]
        linhas.append(
            {
                "id": f"n{i:03d}",
                "fonte": fonte,
                "titulo": f"Notícia {i}",
                "linha_fina": "",
                "texto": texto,
                "url": f"https://exemplo/{i}",
                "data_publicacao": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
                "coletado_em": pd.Timestamp("2026-11-20 12:00")
                if i >= 10
                else pd.Timestamp("2026-09-21"),
            }
        )
    return pd.DataFrame(linhas)


def test_selecionar_v2_fora_do_v1_e_com_gd_sem_solar():
    corpus = corpus_sintetico()
    amostra = r.selecionar_v2(
        corpus, ids_excluir={"n010", "n011"}, tamanho=30, maximo_gd_sem_solar=5
    )
    assert len(amostra) == 30
    assert list(amostra.columns) == r.COLUNAS_V2
    assert not amostra["id"].isin(["n010", "n011"]).any()  # já rotuladas no v1
    assert amostra["gd_sem_solar"].sum() >= 5
    assert (amostra[["relevante", "tom", "observacao"]] == "").all().all()
    assert set(amostra["fonte"]) == {"Agência Brasil", "Agência Gov"}
    assert amostra["id"].is_unique


def test_selecionar_v2_reprodutivel():
    corpus = corpus_sintetico()
    a = r.selecionar_v2(corpus, set(), tamanho=20)
    b = r.selecionar_v2(corpus.sample(frac=1, random_state=1), set(), tamanho=20)
    assert a["id"].tolist() == b["id"].tolist()


def test_selecionar_v2_sem_filtro_de_data_e_sem_ids_fora_v2():
    corpus = corpus_sintetico()
    proibida = next(iter(r.IDS_FORA_V2))
    corpus.loc[0, "id"] = proibida
    amostra = r.selecionar_v2(corpus, set(), tamanho=200)
    assert len(amostra) == len(corpus) - 1  # antigas entram; só a proibida sai
    assert proibida not in set(amostra["id"])
