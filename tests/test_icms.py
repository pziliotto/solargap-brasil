"""Coletor do ICMS: interpretação do texto legal do Convênio 16/15."""

from datetime import date

import pytest

from src.data_acquisition import icms_confaz
from src.preparacao import esquema


@pytest.fixture(scope="module")
def tabela():
    linhas = icms_confaz.REFERENCIA_LOCAL.read_text(encoding="utf-8").splitlines()
    texto = "\n".join(linha for linha in linhas if not linha.lstrip().startswith("#"))
    resultado = icms_confaz.montar_tabela(
        icms_confaz.interpretar_convenio(texto), "referencia_local"
    )
    icms_confaz.validar(resultado)
    return resultado.set_index("sigla_uf")


def test_todas_as_ufs_uma_vez(tabela):
    assert sorted(tabela.index) == sorted(esquema.UFS)


@pytest.mark.parametrize(
    ("uf", "convenio", "data_adesao", "inicio"),
    [
        (
            "GO",
            "16/15",
            date(2015, 5, 14),
            date(2015, 9, 1),
        ),  # original: efeitos só em 09/2015
        ("RN", "44/15", date(2015, 6, 23), date(2015, 9, 1)),
        ("RS", "157/15", date(2015, 12, 30), date(2015, 12, 30)),
        ("PA", "81/16", date(2016, 9, 13), date(2016, 9, 13)),
        ("SE", "75/16", date(2016, 9, 1), date(2016, 9, 1)),  # inferida da redação
        ("AM", "42/18", date(2018, 7, 1), date(2018, 7, 1)),
    ],
)
def test_datas_de_adesao(tabela, uf, convenio, data_adesao, inicio):
    linha = tabela.loc[uf]
    assert linha["convenio_adesao"] == convenio
    assert linha["data_adesao"] == data_adesao and linha["inicio_efeitos"] == inicio


def test_inferencias_sinalizadas(tabela):
    inferidas = tabela[tabela["forma_inclusao"] == "nova redação da cláusula primeira"]
    assert sorted(inferidas.index) == ["PB", "PI", "RO", "SE"]
    assert inferidas["observacao"].str.contains("inferida").all()


def test_paragrafo_3_vale_a_redacao_mais_recente(tabela):
    assert "48 meses" in tabela.loc["PR", "observacao"]
    assert "retirado pelo Conv. ICMS 114/23" in tabela.loc["SC", "observacao"]


def test_texto_sem_datas_falha():
    with pytest.raises(ValueError):
        icms_confaz.interpretar_convenio("Texto qualquer sem as cláusulas esperadas.")
