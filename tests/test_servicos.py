"""Camada de serviços: os indicadores reproduzem a Gold e o crescimento é coerente."""

import pandas as pd
import pytest

from src.preparacao import esquema
from src.servicos import dados, indicadores, noticias, texto


@pytest.fixture(scope="module")
def base():
    agregado = dados.carregar_agregado()
    dim_uf = dados.carregar_uf()
    classes = indicadores.validar_filtros(agregado, 2012, 2026, None)
    tabela = indicadores.indicadores_por_uf(agregado, dim_uf, 2012, 2026, classes, True)
    return agregado, dim_uf, classes, tabela


def test_indicadores_reproduzem_gold_uf(base):
    _, dim_uf, _, tabela = base
    comparado = tabela.merge(dim_uf, on="sigla_uf", suffixes=("", "_gold"))
    assert len(comparado) == esquema.TOTAL_UFS
    assert (
        comparado["qtd_empreendimentos"] == comparado["qtd_empreendimentos_gold"]
    ).all()
    assert (
        comparado["watts_por_habitante"].round(1)
        == comparado["watts_por_habitante_gold"]
    ).all()


def test_criterio_aneel_exclui_imputados(base):
    agregado, dim_uf, classes, tabela = base
    sem = indicadores.indicadores_por_uf(agregado, dim_uf, 2012, 2026, classes, False)
    ma = tabela.set_index("sigla_uf").loc["MA"]
    ma_sem = sem.set_index("sigla_uf").loc["MA"]
    assert ma_sem["qtd_imputados"] == 0
    assert (
        ma["qtd_empreendimentos"] - ma_sem["qtd_empreendimentos"] == ma["qtd_imputados"]
    )


@pytest.mark.parametrize(
    ("inicio", "fim", "classes"),
    [(2025, 2020, None), (1990, 2000, None), (2012, 2026, ("Inexistente",))],
)
def test_filtros_invalidos(base, inicio, fim, classes):
    with pytest.raises(indicadores.FiltroInvalido):
        indicadores.validar_filtros(base[0], inicio, fim, classes)


def test_serie_acumulada_monotona_e_completa(base):
    agregado, _, classes, tabela = base
    serie = indicadores.serie_acumulada(agregado, classes, True)
    ano_min, ano_max = indicadores.anos_disponiveis(agregado)
    assert len(serie) == esquema.TOTAL_UFS * (ano_max - ano_min + 1)
    assert (
        serie.groupby("sigla_uf")["potencia_acumulada_mw"]
        .apply(lambda s: s.is_monotonic_increasing)
        .all()
    )
    final = serie[serie["ano"] == ano_max].set_index("sigla_uf")[
        "potencia_acumulada_mw"
    ]
    assert final.sum() == pytest.approx(tabela["potencia_mw"].sum())


def test_taxa_crescimento_e_janela(base):
    agregado, _, classes, _ = base
    tabela, brasil = indicadores.taxa_crescimento(agregado, classes, True, 2022, 2025)
    rs = tabela.set_index("sigla_uf").loc["RS"]
    esperado = (
        (rs["acumulado_final_mw"] / rs["acumulado_base_mw"]) ** (1 / 3) - 1
    ) * 100
    assert rs["cagr_pct"] == pytest.approx(esperado)
    assert 0 < brasil < 100
    with pytest.raises(indicadores.FiltroInvalido):  # ano final parcial e igual ao base
        indicadores.taxa_crescimento(agregado, classes, True, 2026, 2026)


def test_matriz_classifica_todas_as_ufs(base):
    agregado, _, classes, tabela = base
    crescimento, brasil = indicadores.taxa_crescimento(agregado, classes, True)
    matriz, referencia = indicadores.matriz_oportunidade(tabela, crescimento, brasil)
    assert len(matriz) == esquema.TOTAL_UFS
    assert set(matriz["quadrante"]) <= set(indicadores.DESCRICAO_QUADRANTES)
    emergentes = matriz[matriz["quadrante"] == "Mercado emergente"]
    assert (emergentes["watts_por_habitante"] < referencia["watts_por_habitante"]).all()
    assert (emergentes["cagr_pct"] >= referencia["cagr_pct"]).all()


def test_spearman_sem_scipy():
    x = pd.Series([1, 2, 3, 4, 5])
    assert indicadores.correlacao_spearman(x, x**3) == pytest.approx(1.0)
    assert indicadores.correlacao_spearman(x, -x) == pytest.approx(-1.0)
    assert indicadores.correlacao_spearman(x[:2], x[:2]) is None


def test_texto_para_modelo_respeita_nivel():
    integral = texto.texto_para_modelo(
        "Título", "Linha", "Corpo da notícia", esquema.NIVEL_INTEGRAL
    )
    metadados = texto.texto_para_modelo(
        "Título", "Linha", "Corpo da notícia", esquema.NIVEL_METADADOS
    )
    assert "Corpo" in integral and "Corpo" not in metadados
    longo = texto.texto_para_modelo(
        "T", None, "palavra " * 2000, esquema.NIVEL_INTEGRAL, limite=100
    )
    assert len(longo) <= 106 and longo.endswith("[...]")


def test_detectar_ufs_distingue_mato_grosso():
    assert texto.detectar_ufs("Usinas em Mato Grosso do Sul") == "MS"
    assert texto.detectar_ufs("Mato Grosso e Pará") == "PA,MT"


def test_registrar_noticia_e_duplicidade(tmp_path):
    corpus = dados.carregar_corpus()
    registro = noticias.registrar_noticia(
        fonte="Teste",
        url="https://exemplo.org/noticia-solar-1",
        titulo="Energia solar no Piauí cresce",
        data_publicacao=pd.Timestamp("2026-01-10").date(),
        corpus_atual=corpus,
        pasta_external=tmp_path,
    )
    assert (
        registro["nivel_texto"] == esquema.NIVEL_METADADOS
        and registro["ufs_mencionadas"] == "PI"
    )
    enviadas = dados.carregar_noticias_enviadas(tmp_path)
    assert list(enviadas["id"]) == [registro["id"]]
    completo = dados.carregar_corpus_completo(pasta_external=tmp_path)
    with pytest.raises(noticias.NoticiaDuplicada):
        noticias.registrar_noticia(
            fonte="Teste",
            url="https://exemplo.org/noticia-solar-1",
            titulo="Repetida repetida",
            data_publicacao=pd.Timestamp("2026-01-10").date(),
            corpus_atual=completo,
            pasta_external=tmp_path,
        )
