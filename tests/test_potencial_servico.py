"""Serviço do potencial solar (Tarefa 7) e as três visões da base, sobre a Gold real."""

import numpy as np
import pandas as pd
import pytest

from src.servicos import dados, indicadores, potencial
from src.servicos.dados import DadosIndisponiveis

CAXIAS = "4305108"


@pytest.fixture(scope="module")
def base():
    return potencial.carregar_base()


# ── três visões em indicadores (todas as páginas) ──


def test_normalizar_visao_aceita_booleano_antigo_e_rejeita_desconhecida():
    assert indicadores.normalizar_visao(True) == "corrigida"
    assert indicadores.normalizar_visao(False) == "aneel"
    assert indicadores.normalizar_visao("conservadora") == "conservadora"
    with pytest.raises(indicadores.FiltroInvalido):
        indicadores.normalizar_visao("otimista")


def test_filtrar_usa_a_potencia_de_cada_visao():
    agregado = dados.carregar_agregado()
    classes = tuple(indicadores.classes_disponiveis(agregado))
    total = {
        v: indicadores.filtrar(agregado, 2012, 2026, classes, v)["potencia_kw"].sum()
        for v in indicadores.VISOES
    }
    assert total["corrigida"] == pytest.approx(agregado["potencia_corrigida_kw"].sum())
    assert total["conservadora"] == pytest.approx(
        agregado["potencia_conservadora_kw"].sum()
    )
    oficial = agregado.loc[~agregado["fonte_imputada"], "potencia_kw"].sum()
    assert total["aneel"] == pytest.approx(oficial)
    # Corrigir só os residenciais fica entre a correção completa e o dado oficial
    assert total["corrigida"] < total["conservadora"] < total["aneel"]
    # O booleano antigo continua valendo (API de indicadores)
    assert indicadores.filtrar(agregado, 2012, 2026, classes, True)[
        "potencia_kw"
    ].sum() == pytest.approx(total["corrigida"])


# ── recortes e totais ──


def test_resumo_reproduz_a_gold_de_potencial(base):
    for visao, coluna in [
        ("corrigida", "taxa_realizacao"),
        ("aneel", "taxa_realizacao_aneel"),
        ("conservadora", "taxa_realizacao_conservador"),
    ]:
        tabela = potencial.tabela_uf(base, visao).set_index("uf")
        gold = base.uf.set_index("uf")
        assert len(tabela) == 27
        assert np.allclose(tabela["taxa_realizacao"], gold.loc[tabela.index, coluna])
        assert np.allclose(tabela["x_mwh_ano"], gold.loc[tabela.index, "x_mwh_ano"])
        brasil = potencial.resumo_recorte(base, visao)
        assert brasil["gap_mwh_ano"] == pytest.approx(
            brasil["x_mwh_ano"] - brasil["y_mwh_ano"]
        )
        assert brasil["taxa_realizacao"] == pytest.approx(
            base.municipal[potencial.COLUNAS_VISAO[visao]["y"]].sum()
            / base.municipal["x_mwh_ano"].sum()
        )


def test_visao_muda_y_mas_nao_x(base):
    pr = {v: potencial.resumo_recorte(base, v, uf="PR") for v in indicadores.VISOES}
    assert pr["corrigida"]["x_mwh_ano"] == pr["aneel"]["x_mwh_ano"]
    # Os 75 kW da COPEL-DIS inflam o PR no dado oficial
    assert pr["aneel"]["taxa_realizacao"] > pr["conservadora"]["taxa_realizacao"]
    assert pr["conservadora"]["taxa_realizacao"] > pr["corrigida"]["taxa_realizacao"]


def test_recorte_inexistente(base):
    with pytest.raises(potencial.RecorteInexistente):
        potencial.resumo_recorte(base, cod_ibge="9999999")
    with pytest.raises(potencial.RecorteInexistente):
        potencial.validar_uf(base, "XX")
    assert potencial.validar_uf(base, "rs") == "RS"


def test_municipios_da_uf_em_ordem_alfabetica(base):
    lista = potencial.municipios_da_uf(base, "RS")
    assert len(lista) == 497 and lista["nome"].is_monotonic_increasing


# ── explicação (SHAP) ──


def test_explicacao_municipio_ordenada_e_aditiva(base):
    explicacao = potencial.explicar(base, cod_ibge=CAXIAS)
    contribuicoes = [f["contribuicao"] for f in explicacao["fatores"]]
    assert len(contribuicoes) == 12
    assert [abs(c) for c in contribuicoes] == sorted(
        (abs(c) for c in contribuicoes), reverse=True
    )
    # SHAP é aditivo: base + contribuições = previsão
    assert explicacao["valor_base"] + sum(contribuicoes) == pytest.approx(
        explicacao["taxa_prevista"], abs=1e-6
    )
    primeiro = explicacao["fatores"][0]
    assert (
        primeiro["fator"] == "log_densidade_hab_km2" and primeiro["efeito"] == "reduz"
    )
    assert primeiro["frase"].startswith("Densidade demográfica, 280,5 hab/km²: reduz")
    assert "densidade demográfica" in explicacao["leitura"]
    assert explicacao["aviso_visao"] is None


def test_explicacao_uf_reproduz_shap_uf(base):
    gold = pd.read_parquet(dados.PASTA_PROCESSED / "shap_uf.parquet").set_index("uf")
    for uf in ("RS", "PR", "MA"):
        explicacao = potencial.explicar(base, uf=uf)
        for fator in explicacao["fatores"]:
            assert fator["contribuicao"] == pytest.approx(
                gold.loc[uf, f"shap_{fator['fator']}"]
            )
        assert explicacao["taxa_prevista"] == pytest.approx(gold.loc[uf, "previsao"])


def test_explicacao_em_outra_visao_avisa_e_traz_ranking_da_visao(base):
    corrigida = potencial.explicar(base, "corrigida", cod_ibge="4118204")  # Paranaguá
    aneel = potencial.explicar(base, "aneel", cod_ibge="4118204")
    assert aneel["aviso_visao"] and aneel["visao_modelo"] == "corrigida"
    assert [f["contribuicao"] for f in aneel["fatores"]] == [
        f["contribuicao"] for f in corrigida["fatores"]
    ]
    assert aneel["taxa_observada"] != corrigida["taxa_observada"]
    robustez = base.robustez[base.robustez["visao"] == "aneel"].sort_values("rank")
    assert aneel["ranking_global_visao"][0] == (
        potencial.FATORES[robustez["fator"].iloc[0]].rotulo
    )


# ── cenários ──


def test_cenarios_municipio_batem_com_a_gold_e_taxa_constante(base):
    tabela = potencial.cenarios_municipio(base, CAXIAS, "corrigida")
    gold = base.projecao_municipal[
        base.projecao_municipal["cod_ibge"] == CAXIAS
    ].sort_values(["cenario", "janela"])
    assert len(tabela) == 4
    assert np.allclose(tabela["y_projetado_mwh_ano"], gold["y_projetado_mwh_ano"])
    assert np.allclose(
        tabela["gap_projetado_min_mwh_ano"], gold["gap_projetado_min_mwh_ano"]
    )
    assert np.allclose(tabela["taxa_projetada"], tabela["taxa_realizacao"])


def test_cenarios_conservadora_derivada_pela_razao_da_corrigida(base):
    cod = "4118204"  # Paranaguá: y difere entre as visões
    conservadora = potencial.cenarios_municipio(base, cod, "conservadora")
    linha = potencial.linha_municipio(base, cod)
    esperado = linha["y_conservador_mwh_ano"] * (1 + conservadora["delta_mediano"])
    assert np.allclose(conservadora["y_projetado_mwh_ano"], esperado)
    assert np.allclose(conservadora["taxa_projetada"], conservadora["taxa_realizacao"])
    assert (
        conservadora["gap_projetado_min_mwh_ano"]
        <= conservadora["gap_projetado_mwh_ano"]
    ).all()
    assert (
        conservadora["gap_projetado_mwh_ano"]
        <= conservadora["gap_projetado_max_mwh_ano"]
    ).all()


def test_cenarios_uf_alinhados_por_uf(base):
    tabela = potencial.cenarios_uf(base, "aneel").set_index(["uf", "cenario", "janela"])
    gold = base.projecao_uf.set_index(["uf", "cenario", "janela"])
    assert len(tabela) == 108
    assert np.allclose(tabela["delta_mediano"], gold.loc[tabela.index, "delta_mediano"])
    assert np.allclose(
        tabela["y_projetado_mwh_ano"],
        gold.loc[tabela.index, "y_aneel_projetado_mwh_ano"],
    )


# ── carga ──


def test_gold_ausente_levanta_dados_indisponiveis(tmp_path):
    with pytest.raises(DadosIndisponiveis):
        potencial.carregar_base(pasta=tmp_path)


def test_malhas_do_mapa_cobrem_as_ufs(base):
    import json

    ufs = json.loads(potencial.caminho_malha().read_text(encoding="utf-8"))
    assert {f["properties"]["uf"] for f in ufs["features"]} == set(base.municipal["uf"])
    rs = json.loads(potencial.caminho_malha("RS").read_text(encoding="utf-8"))
    codigos = {f["properties"]["cod_ibge"] for f in rs["features"]}
    assert codigos == set(base.municipal.loc[base.municipal["uf"] == "RS", "cod_ibge"])
    with pytest.raises(DadosIndisponiveis):
        potencial.caminho_malha("XX")
