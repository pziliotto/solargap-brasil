"""
Testes da irradiação municipal (TP4.5): encaixe na grade do NASA POWER,
deduplicação de células, cache Bronze, tratamento do -999 e média ponderada.

Nenhum teste acessa a rede: as respostas do POWER vêm de tests/fixtures
(power_celula_completa.json é uma resposta real, da célula centrada em
-22,5 / -45,5; power_celula_com_preenchimento.json é a mesma resposta com três
meses trocados pelo -999) e as requisições são substituídas por objetos falsos.
"""

from __future__ import annotations

import calendar
import json
import math

import numpy as np
import pandas as pd
import pytest
import requests

from src.data_acquisition import coletor_nasa_power as power
from src.potencial import config, irradiacao


@pytest.fixture
def payload_completo(fixture):
    return json.loads(fixture("power_celula_completa.json"))


@pytest.fixture
def payload_com_preenchimento(fixture):
    return json.loads(fixture("power_celula_com_preenchimento.json"))


@pytest.fixture
def cache_temporario(tmp_path, monkeypatch):
    """Redireciona o cache Bronze para uma pasta temporária."""
    monkeypatch.setattr(config, "PASTA_RAW_POWER", tmp_path / "nasa_power")
    return tmp_path / "nasa_power"


def _pontos(*linhas):
    return pd.DataFrame(linhas, columns=["cod_ibge", "nome", "uf", "lat", "lon"])


# ═══════════════════ Encaixe na grade ═══════════════════


@pytest.mark.parametrize(
    "coordenada, centro",
    [
        (-22.1, -22.5),
        (-22.95, -22.5),
        (-22.0, -21.5),  # borda pertence à célula de cima (conferido no POWER)
        (-21.95, -21.5),
        (-45.0, -44.5),
        (-45.99, -45.5),
        (0.3, 0.5),
        (-0.3, -0.5),
        (0.0, 0.5),
        (5.27, 5.5),
    ],
)
def test_encaixe_na_grade_de_1_grau(coordenada, centro):
    assert power.encaixar_na_grade(coordenada) == centro


def test_encaixe_respeita_outra_resolucao():
    assert power.encaixar_na_grade(-22.1, resolucao=0.5) == -22.25
    assert power.encaixar_na_grade(-22.6, resolucao=0.5) == -22.75


def test_id_celula_formato_estavel():
    assert power.id_celula(-22.5, -45.5) == "lat-22.5_lon-45.5"
    assert power.id_celula(0.5, -48.5) == "lat0.5_lon-48.5"


# ═══════════════════ Deduplicação ═══════════════════


def test_municipios_na_mesma_celula_compartilham_uma_consulta():
    pontos = _pontos(
        ("3500001", "A", "SP", -22.10, -45.10),
        ("3500002", "B", "SP", -22.90, -45.90),  # mesma célula de A
        ("3500003", "C", "SP", -21.90, -45.10),  # célula ao norte
        ("3500004", "D", "SP", -22.50, -44.20),  # célula a leste
    )
    com_celula = power.atribuir_celulas(pontos)
    assert com_celula.loc[0, "celula_power"] == com_celula.loc[1, "celula_power"]

    celulas = power.celulas_unicas(com_celula)
    assert len(celulas) == 3
    contagem = dict(zip(celulas["celula_power"], celulas["n_municipios"]))
    assert contagem["lat-22.5_lon-45.5"] == 2
    assert contagem["lat-21.5_lon-45.5"] == 1
    assert contagem["lat-22.5_lon-44.5"] == 1


def test_coleta_consulta_cada_celula_uma_vez_e_reusa_cache(
    cache_temporario, monkeypatch, payload_completo
):
    chamadas = []

    def falso_baixar(lat, lon, anos=config.ANOS_BASE):
        chamadas.append((lat, lon))
        return payload_completo

    monkeypatch.setattr(power, "baixar_celula", falso_baixar)
    pontos = _pontos(
        ("3500001", "A", "SP", -22.1, -45.1),
        ("3500002", "B", "SP", -22.9, -45.9),
        ("3500003", "C", "SP", -21.9, -45.1),
    )
    celulas = power.celulas_unicas(power.atribuir_celulas(pontos))

    primeira = power.coletar_celulas(celulas)
    assert primeira == {"cache": 0, "baixada": 2, "falha": 0}
    assert sorted(chamadas) == [(-22.5, -45.5), (-21.5, -45.5)]  # pelo centro

    segunda = power.coletar_celulas(celulas)
    assert segunda == {"cache": 2, "baixada": 0, "falha": 0}
    assert len(chamadas) == 2  # nada baixado de novo
    assert not list(cache_temporario.glob("*.tmp"))


def test_coleta_falha_alto_se_alguma_celula_ficar_sem_dado(cache_temporario, monkeypatch):
    def sempre_falha(lat, lon, anos=config.ANOS_BASE):
        raise requests.exceptions.ConnectionError("sem rede")

    monkeypatch.setattr(power, "baixar_celula", sempre_falha)
    celulas = power.celulas_unicas(
        power.atribuir_celulas(_pontos(("3500001", "A", "SP", -22.1, -45.1)))
    )
    with pytest.raises(RuntimeError, match="1 célula"):
        power.coletar_celulas(celulas)


# ═══════════════════ Cache Bronze ═══════════════════


def test_cache_corrompido_ou_incompleto_e_ignorado(cache_temporario, payload_completo):
    caminho = power.caminho_cache("lat-22.5_lon-45.5")
    caminho.parent.mkdir(parents=True)

    caminho.write_text("{ truncado", encoding="utf-8")
    assert power.ler_cache(caminho) is None

    incompleto = json.loads(json.dumps(payload_completo))
    del incompleto["properties"]["parameter"][power.PARAMETRO]["202506"]
    caminho.write_text(json.dumps(incompleto), encoding="utf-8")
    assert power.ler_cache(caminho) is None

    power.gravar_cache(payload_completo, caminho)
    assert power.ler_cache(caminho) == payload_completo


def test_nome_do_cache_inclui_o_periodo(cache_temporario):
    caminho = power.caminho_cache("lat-22.5_lon-45.5", anos=(2023, 2024, 2025))
    assert caminho.name == "lat-22.5_lon-45.5_2023_2025.json"


# ═══════════════════ Requisição (retry sem rede) ═══════════════════


class _RespostaFalsa:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}", response=self)


class _SessaoFalsa:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []

    def get(self, url, params=None, timeout=None):
        self.pedidos.append(params)
        return self.respostas.pop(0)


def test_retry_em_503_e_429_depois_sucesso(monkeypatch, payload_completo):
    sessao = _SessaoFalsa(
        [_RespostaFalsa(503), _RespostaFalsa(429), _RespostaFalsa(200, payload_completo)]
    )
    esperas = []
    monkeypatch.setattr(power, "_sessao", lambda: sessao)
    monkeypatch.setattr(power.time, "sleep", esperas.append)

    assert power.baixar_celula(-22.5, -45.5) == payload_completo
    assert esperas == [2, 4]  # backoff exponencial
    pedido = sessao.pedidos[0]
    assert pedido["parameters"] == "ALLSKY_SFC_SW_DWN"
    assert pedido["community"] == "RE"
    assert (pedido["start"], pedido["end"]) == ("2023", "2025")


def test_erro_4xx_da_consulta_nao_e_retentado(monkeypatch):
    sessao = _SessaoFalsa([_RespostaFalsa(422)])
    monkeypatch.setattr(power, "_sessao", lambda: sessao)
    monkeypatch.setattr(power.time, "sleep", lambda s: None)
    with pytest.raises(requests.exceptions.HTTPError):
        power.baixar_celula(-22.5, -45.5)
    assert len(sessao.pedidos) == 1


def test_user_agent_identifica_o_projeto():
    sessao = power._sessao()
    assert sessao.headers["User-Agent"].startswith("SolarGapBrasil")


# ═══════════════════ Tratamento do -999 ═══════════════════


def test_valor_de_preenchimento_vira_ausente(payload_com_preenchimento):
    serie = irradiacao.extrair_serie_mensal(payload_com_preenchimento)
    assert len(serie) == 36  # mês 13 (média anual) descartado
    ausentes = set(serie[serie.isna()].index)
    assert ausentes == {(2023, 2), (2024, 2), (2025, 12)}
    assert (serie.dropna() > 0).all()


def test_fill_value_padrao_quando_cabecalho_nao_declara(payload_com_preenchimento):
    del payload_com_preenchimento["header"]
    serie = irradiacao.extrair_serie_mensal(payload_com_preenchimento)
    assert serie.isna().sum() == 3


def test_meses_com_preenchimento_ficam_fora_da_media(
    payload_completo, payload_com_preenchimento
):
    media, n_validos = irradiacao.media_ponderada_por_dias(
        irradiacao.extrair_serie_mensal(payload_com_preenchimento)
    )
    assert n_validos == 33

    completa = irradiacao.extrair_serie_mensal(payload_completo)
    sem_lacunas = completa.drop([(2023, 2), (2024, 2), (2025, 12)])
    esperado, _ = irradiacao.media_ponderada_por_dias(sem_lacunas)
    assert media == pytest.approx(esperado)
    assert 3.5 < media < 6.5  # -999 contaminaria a média


# ═══════════════════ Média ponderada pelos dias ═══════════════════


def test_media_ponderada_pelos_dias_do_mes():
    # Janeiro (31 dias) = 4,0 e fevereiro de 2024 (bissexto, 29 dias) = 6,0
    serie = pd.Series(
        [4.0, 6.0], index=pd.MultiIndex.from_tuples([(2024, 1), (2024, 2)])
    )
    media, n_validos = irradiacao.media_ponderada_por_dias(serie)
    assert media == pytest.approx((4 * 31 + 6 * 29) / 60)
    assert media != pytest.approx(5.0)  # difere da média simples
    assert n_validos == 2


def test_media_ponderada_36_meses_reproduz_energia_do_periodo(payload_completo):
    serie = irradiacao.extrair_serie_mensal(payload_completo)
    media, n_validos = irradiacao.media_ponderada_por_dias(serie)
    assert n_validos == 36

    dias_totais = sum(calendar.monthrange(a, m)[1] for a, m in serie.index)
    assert dias_totais == 1096  # 2024 é bissexto
    energia = sum(
        v * calendar.monthrange(a, m)[1] for (a, m), v in serie.items()
    )
    assert media == pytest.approx(energia / dias_totais)


def test_media_sem_meses_validos_e_nan():
    serie = pd.Series(
        [np.nan, np.nan], index=pd.MultiIndex.from_tuples([(2023, 1), (2023, 2)])
    )
    media, n_validos = irradiacao.media_ponderada_por_dias(serie)
    assert math.isnan(media) and n_validos == 0


# ═══════════════════ Silver e validação ═══════════════════


def _silver_sintetica(payload):
    pontos = _pontos(
        ("3500001", "A", "SP", -22.1, -45.1),
        ("3500002", "B", "SP", -22.9, -45.9),
        ("3500003", "C", "SP", -21.9, -45.1),  # célula sem payload
    )
    return irradiacao.montar_silver(pontos, {"lat-22.5_lon-45.5": payload})


def test_silver_tem_colunas_do_contrato(payload_completo):
    silver = _silver_sintetica(payload_completo)
    assert list(silver.columns) == irradiacao.COLUNAS_SILVER
    a, b, c = silver.itertuples(index=False)
    assert a.irradiacao_kwh_m2_dia == b.irradiacao_kwh_m2_dia
    assert a.n_meses_validos == 36
    assert math.isnan(c.irradiacao_kwh_m2_dia) and c.n_meses_validos == 0


def test_validacao_aponta_municipio_sem_valor_e_fora_da_faixa(payload_completo):
    silver = _silver_sintetica(payload_completo)
    silver.loc[0, "irradiacao_kwh_m2_dia"] = 7.2
    problemas = " | ".join(irradiacao.validar_silver(silver))
    assert "1 município(s) sem irradiação" in problemas
    assert "fora da faixa" in problemas


def test_validacao_exige_nordeste_e_centro_oeste_acima_do_sul():
    silver = pd.DataFrame(
        {
            "cod_ibge": ["2900001", "5200001", "4300001"],
            "uf": ["BA", "GO", "RS"],
            "irradiacao_kwh_m2_dia": [4.0, 5.5, 5.0],
            "n_meses_validos": [36, 36, 36],
            "celula_power": ["x", "y", "z"],
        }
    )
    problemas = irradiacao.validar_silver(silver)
    assert any("Nordeste" in p for p in problemas)
    assert not any("Centro-Oeste" in p for p in problemas)


# ═══════════════════ Ponto representativo ═══════════════════


def test_ponto_representativo_fica_dentro_de_poligono_concavo():
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Polygon

    # Polígono em "C": o centroide cai no vão, fora do município
    formato_c = Polygon([(0, 0), (3, 0), (3, 1), (1, 1), (1, 2), (3, 2), (3, 3), (0, 3)])
    assert not formato_c.contains(formato_c.centroid)

    malha = gpd.GeoDataFrame(
        {
            "code_muni": [3500001.0],
            "name_muni": ["Município C"],
            "abbrev_state": ["SP"],
        },
        geometry=[formato_c],
        crs="EPSG:4674",
    )
    from src.potencial.malha_municipal import calcular_pontos

    tabela = calcular_pontos(malha)
    assert tabela.loc[0, "cod_ibge"] == "3500001"
    from shapely.geometry import Point

    assert formato_c.contains(Point(tabela.loc[0, "lon"], tabela.loc[0, "lat"]))
