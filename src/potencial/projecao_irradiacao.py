"""
PROJETO: SolarGap Brasil
ARQUIVO: potencial/projecao_irradiacao.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Projeção da irradiação municipal para 2030–2050 (TP4.5, Tarefa 6), pelo
    método delta sobre o rsds do NEX-GDDP-CMIP6 v2.0 (5 modelos, SSP2-4.5 e
    SSP5-8.5), e o efeito sobre o potencial técnico (x) e o gap.

MÉTODO DELTA (por modelo, em cada célula de 0,25°):
    historico = média do rsds diário de 1995–2014 (cenário historical)
    futuro    = média de 2030–2039 ou de 2040–2050 (ssp245 ou ssp585)
    delta     = futuro / historico − 1
    O modelo só informa a VARIAÇÃO relativa; o nível continua sendo o
    observado: H_projetada = H_observada x (1 + delta), com H_observada = média
    NASA POWER 2023–2025 (irradiacao_municipal.parquet). Assim o viés absoluto
    de cada modelo não entra na projeção.

MUNICÍPIO -> CÉLULA:
    Cada município (ponto de municipios_pontos.parquet) usa a célula de 0,25°
    mais próxima COM DADO (o NEX-GDDP não tem valor sobre o mar; um município
    costeiro pode cair numa célula oceânica). A distância fica registrada.

ENSEMBLE:
    Para cada município, cenário e janela: mediana, mínimo e máximo entre os 5
    modelos. x, y e gap são lineares em H, então a mediana de x é o x da
    mediana do delta. No gap, o mínimo e o máximo são tomados entre os modelos
    (o sinal do gap pode inverter a ordem quando y > x).
    Por UF, cada modelo é agregado primeiro (Σx, Σy, Σgap) e só depois se
    tomam mediana, mínimo e máximo entre modelos.

O QUE NÃO MUDA:
    A capacidade instalada (kWp) fica no valor atual, e a taxa de realização
    y/x não muda com a irradiação: x e y usam o mesmo H, que se cancela
    (taxa = kWp instalado / kWp potencial). A projeção altera o MWh/ano de
    x, y e gap, não a taxa.

VISÕES:
    Visão corrigida como padrão (y_projetado, gap_projetado); critério ANEEL
    em colunas *_aneel.

SAÍDAS:
    data/interim/potencial/cmip6_delta_rsds_celulas.parquet (delta por célula)
    data/processed/projecao_irradiacao_municipal.parquet
    data/processed/projecao_irradiacao_uf.parquet

OBS. DE USO:
    python -m src.data_acquisition.coletor_cmip6      # recortes (~5,8 GB)
    python -m src.potencial.projecao_irradiacao
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from src.data_acquisition import coletor_cmip6 as cmip6
from src.data_acquisition.coletor_base import configurar_logging
from src.potencial import config
from src.potencial.potencial_municipal import energia_mwh_ano

RAIO_TERRA_KM = 6371.0
VALOR_AUSENTE_MINIMO = 1e19  # _FillValue do NEX-GDDP é 1e20

# ═══════════════════ Funções puras (testáveis sem rede) ═══════════════════


def media_temporal(diario: np.ndarray) -> np.ndarray:
    """Média no eixo 0 (dias ou anos); célula sem nenhum valor fica NaN."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # célula toda NaN (mar)
        return np.nanmean(diario, axis=0)


def delta_relativo(historico: np.ndarray, futuro: np.ndarray) -> np.ndarray:
    """futuro / historico − 1; NaN onde o histórico é ausente ou não positivo."""
    historico = np.asarray(historico, dtype="float64")
    futuro = np.asarray(futuro, dtype="float64")
    valido = np.isfinite(historico) & np.isfinite(futuro) & (historico > 0)
    delta = np.full(np.broadcast(historico, futuro).shape, np.nan)
    np.divide(futuro, historico, out=delta, where=valido)
    return np.where(valido, delta - 1, np.nan)


def resumo_ensemble(deltas: np.ndarray) -> dict[str, np.ndarray]:
    """Mediana, mínimo e máximo entre modelos (eixo 0). Um NaN propaga."""
    deltas = np.asarray(deltas, dtype="float64")
    return {
        "mediano": np.median(deltas, axis=0),
        "min": deltas.min(axis=0),
        "max": deltas.max(axis=0),
    }


def celula_mais_proxima(
    lat_pontos: np.ndarray,
    lon_pontos: np.ndarray,
    lat_grade: np.ndarray,
    lon_grade: np.ndarray,
    valido: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Índices (i, j) da célula válida mais próxima de cada ponto e a distância (km).

    lat_grade e lon_grade são os eixos 1-D da grade; valido é a máscara 2-D
    (lat x lon) das células com dado. Distância de grande círculo (haversine).
    """
    from sklearn.neighbors import BallTree

    ii, jj = np.nonzero(valido)
    if ii.size == 0:
        raise ValueError("Nenhuma célula válida na grade.")
    celulas = np.radians(np.column_stack([lat_grade[ii], lon_grade[jj]]))
    pontos = np.radians(np.column_stack([lat_pontos, lon_pontos]))
    distancia, indice = BallTree(celulas, metric="haversine").query(pontos, k=1)
    indice = indice[:, 0]
    return ii[indice], jj[indice], distancia[:, 0] * RAIO_TERRA_KM


def lon_180(lon: np.ndarray) -> np.ndarray:
    """Longitude de 0..360 para −180..180."""
    lon = np.asarray(lon, dtype="float64")
    return np.where(lon > 180, lon - 360, lon)


def projetar(base: pd.DataFrame, deltas_por_modelo: pd.DataFrame) -> pd.DataFrame:
    """x, y e gap projetados por modelo (uma linha por município x modelo).

    base: cod_ibge, uf, irradiacao_kwh_m2_dia (H observada), kwp_potencial,
          kwp_local_res_rural, kwp_local_res_rural_aneel.
    deltas_por_modelo: cod_ibge, modelo, delta.
    A capacidade (kWp) não muda; só H.
    """
    tabela = deltas_por_modelo.merge(
        base, on="cod_ibge", how="left", validate="many_to_one"
    )
    h = tabela["irradiacao_kwh_m2_dia"] * (1 + tabela["delta"])
    tabela["H_projetada"] = h
    tabela["x_projetado_mwh_ano"] = energia_mwh_ano(tabela["kwp_potencial"], h)
    tabela["y_projetado_mwh_ano"] = energia_mwh_ano(tabela["kwp_local_res_rural"], h)
    tabela["y_aneel_projetado_mwh_ano"] = energia_mwh_ano(
        tabela["kwp_local_res_rural_aneel"], h
    )
    tabela["gap_projetado_mwh_ano"] = (
        tabela["x_projetado_mwh_ano"] - tabela["y_projetado_mwh_ano"]
    )
    tabela["gap_aneel_projetado_mwh_ano"] = (
        tabela["x_projetado_mwh_ano"] - tabela["y_aneel_projetado_mwh_ano"]
    )
    return tabela


GRANDEZAS = [
    "delta",
    "H_projetada",
    "x_projetado_mwh_ano",
    "y_projetado_mwh_ano",
    "y_aneel_projetado_mwh_ano",
    "gap_projetado_mwh_ano",
    "gap_aneel_projetado_mwh_ano",
]


def _nome(grandeza: str, estatistica: str) -> str:
    """delta -> delta_mediano/delta_min/delta_max; x_projetado_mwh_ano -> x_projetado_min_mwh_ano."""
    if grandeza in ("delta", "H_projetada"):
        return (
            grandeza
            if (grandeza, estatistica) == ("H_projetada", "mediano")
            else (f"{grandeza}_{estatistica}")
        )
    raiz = grandeza.removesuffix("_mwh_ano")
    return (
        f"{grandeza}" if estatistica == "mediano" else f"{raiz}_{estatistica}_mwh_ano"
    )


def resumir_modelos(por_modelo: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    """Mediana, mínimo e máximo entre modelos de cada grandeza, por chave."""
    grupos = por_modelo.groupby(chaves)[GRANDEZAS]
    partes = {
        "mediano": grupos.median(),
        "min": grupos.min(),
        "max": grupos.max(),
    }
    saida = pd.DataFrame(index=partes["mediano"].index)
    for grandeza in GRANDEZAS:
        for estatistica, tabela in partes.items():
            saida[_nome(grandeza, estatistica)] = tabela[grandeza]
    saida["n_modelos"] = grupos.size()
    return saida.reset_index()


# ═══════════════════ Leitura do cache (Bronze) ═══════════════════


def ler_media_anual(caminho: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(lat, lon −180..180, média anual em W/m²) de um recorte do cache."""
    import h5py

    with h5py.File(caminho, "r") as arquivo:
        dados = arquivo[cmip6.VARIAVEL][:].astype("float64")
        lat = arquivo["lat"][:].astype("float64")
        lon = lon_180(arquivo["lon"][:])
    dados[dados > VALOR_AUSENTE_MINIMO] = np.nan
    return lat, lon, media_temporal(dados)


def climatologia(modelo: str, cenario: str, anos: tuple[int, int]) -> tuple:
    """Média das médias anuais de um período. Falha alto se faltar um ano."""
    medias, grade = [], None
    faltando = []
    for ano in range(anos[0], anos[1] + 1):
        caminho = cmip6.caminho_cache(cmip6.Pedido(modelo, cenario, ano))
        if not caminho.exists():
            faltando.append(ano)
            continue
        lat, lon, media = ler_media_anual(caminho)
        if grade is None:
            grade = (lat, lon)
        elif not (np.allclose(grade[0], lat) and np.allclose(grade[1], lon)):
            raise ValueError(f"Grade diferente em {caminho.name}")
        medias.append(media)
    if faltando:
        raise FileNotFoundError(
            f"{modelo} {cenario}: faltam {len(faltando)} ano(s) no cache "
            f"({faltando[:5]}...). Rode python -m src.data_acquisition.coletor_cmip6"
        )
    return grade[0], grade[1], media_temporal(np.stack(medias))


def deltas_por_celula() -> tuple[np.ndarray, np.ndarray, dict, dict]:
    """Delta de cada modelo, cenário e janela; e a climatologia histórica (W/m²)."""
    deltas, historicos, grade = {}, {}, None
    for modelo in cmip6.MODELOS:
        lat, lon, historico = climatologia(
            modelo, "historical", config.PERIODO_HISTORICO_CMIP6
        )
        if grade is None:
            grade = (lat, lon)
        elif not (np.allclose(grade[0], lat) and np.allclose(grade[1], lon)):
            raise ValueError(f"Grade de {modelo} difere dos demais modelos.")
        historicos[modelo] = historico
        for cenario in config.CENARIOS_PROJECAO:
            for janela, anos in config.JANELAS_PROJECAO.items():
                _, _, futuro = climatologia(modelo, cenario, anos)
                deltas[(modelo, cenario, janela)] = delta_relativo(historico, futuro)
        logging.info("%s: climatologias e deltas calculados", modelo)
    return grade[0], grade[1], deltas, historicos


# ═══════════════════ Montagem das Gold ═══════════════════

COLUNAS_BASE = [
    "cod_ibge",
    "uf",
    "irradiacao_kwh_m2_dia",
    "kwp_potencial",
    "kwp_local_res_rural",
    "kwp_local_res_rural_aneel",
    "x_mwh_ano",
    "y_mwh_ano",
    "y_aneel_mwh_ano",
    "gap_mwh_ano",
    "taxa_realizacao",
    "taxa_realizacao_aneel",
]


def tabela_deltas_municipais(
    pontos: pd.DataFrame, lat: np.ndarray, lon: np.ndarray, deltas: dict
) -> pd.DataFrame:
    """cod_ibge x modelo x cenário x janela com o delta da célula mais próxima."""
    valido = np.logical_and.reduce([np.isfinite(d) for d in deltas.values()])
    i, j, distancia = celula_mais_proxima(
        pontos["lat"].to_numpy(), pontos["lon"].to_numpy(), lat, lon, valido
    )
    linhas = []
    for (modelo, cenario, janela), grade in deltas.items():
        linhas.append(
            pd.DataFrame(
                {
                    "cod_ibge": pontos["cod_ibge"].to_numpy(),
                    "modelo": modelo,
                    "cenario": cenario,
                    "janela": janela,
                    "delta": grade[i, j],
                    "celula_lat": lat[i],
                    "celula_lon": lon[j],
                    "distancia_celula_km": distancia,
                }
            )
        )
    return pd.concat(linhas, ignore_index=True)


def montar_municipal(base: pd.DataFrame, deltas_mun: pd.DataFrame) -> pd.DataFrame:
    chaves = ["cod_ibge", "cenario", "janela"]
    por_modelo = projetar(base, deltas_mun[[*chaves, "modelo", "delta"]])
    resumo = resumir_modelos(por_modelo, chaves)
    celula = deltas_mun.drop_duplicates("cod_ibge")[
        ["cod_ibge", "celula_lat", "celula_lon", "distancia_celula_km"]
    ]
    gold = resumo.merge(base, on="cod_ibge", validate="many_to_one").merge(
        celula, on="cod_ibge", validate="many_to_one"
    )
    gold = gold.rename(columns={"irradiacao_kwh_m2_dia": "H_observada"})
    primeiras = [
        "cod_ibge",
        "uf",
        "cenario",
        "janela",
        "delta_mediano",
        "delta_min",
        "delta_max",
        "H_observada",
        "H_projetada",
        "H_projetada_min",
        "H_projetada_max",
        "x_projetado_mwh_ano",
        "x_projetado_min_mwh_ano",
        "x_projetado_max_mwh_ano",
        "y_projetado_mwh_ano",
        "y_projetado_min_mwh_ano",
        "y_projetado_max_mwh_ano",
        "gap_projetado_mwh_ano",
        "gap_projetado_min_mwh_ano",
        "gap_projetado_max_mwh_ano",
        "y_aneel_projetado_mwh_ano",
        "gap_aneel_projetado_mwh_ano",
        "gap_aneel_projetado_min_mwh_ano",
        "gap_aneel_projetado_max_mwh_ano",
        "x_mwh_ano",
        "y_mwh_ano",
        "y_aneel_mwh_ano",
        "gap_mwh_ano",
        "taxa_realizacao",
        "taxa_realizacao_aneel",
        "n_modelos",
        "celula_lat",
        "celula_lon",
        "distancia_celula_km",
    ]
    return gold[primeiras].sort_values(chaves).reset_index(drop=True)


def montar_uf(base: pd.DataFrame, deltas_mun: pd.DataFrame) -> pd.DataFrame:
    """Agrega cada modelo por UF e só depois resume entre modelos."""
    chaves = ["uf", "cenario", "janela"]
    por_modelo = projetar(
        base, deltas_mun[["cod_ibge", "modelo", "cenario", "janela", "delta"]]
    )
    somas = por_modelo.groupby([*chaves, "modelo"], as_index=False)[
        [
            "x_projetado_mwh_ano",
            "y_projetado_mwh_ano",
            "y_aneel_projetado_mwh_ano",
            "gap_projetado_mwh_ano",
            "gap_aneel_projetado_mwh_ano",
        ]
    ].sum()
    observado = base.groupby("uf")[
        ["x_mwh_ano", "y_mwh_ano", "y_aneel_mwh_ano", "gap_mwh_ano"]
    ].sum()
    somas = somas.join(observado, on="uf")
    # Delta da UF = variação do potencial x (irradiação ponderada pelo potencial)
    somas["delta"] = somas["x_projetado_mwh_ano"] / somas["x_mwh_ano"] - 1
    h_obs = base.groupby("uf").apply(
        lambda g: np.average(g["irradiacao_kwh_m2_dia"], weights=g["kwp_potencial"]),
        include_groups=False,
    )
    somas["H_projetada"] = somas["uf"].map(h_obs) * (1 + somas["delta"])
    uf = resumir_modelos(somas, chaves)
    uf = uf.join(observado, on="uf")
    uf["H_observada"] = uf["uf"].map(h_obs)
    uf["taxa_realizacao"] = uf["y_mwh_ano"] / uf["x_mwh_ano"]
    uf["taxa_realizacao_aneel"] = uf["y_aneel_mwh_ano"] / uf["x_mwh_ano"]
    return uf.sort_values(chaves).reset_index(drop=True)


def alertas_sanidade(
    deltas_mun: pd.DataFrame, limite: float = config.LIMITE_ALERTA_DELTA
) -> pd.DataFrame:
    """Combinações município x modelo x cenário x janela com |delta| > limite."""
    return deltas_mun[deltas_mun["delta"].abs() > limite]


def tabela_celulas(
    lat: np.ndarray, lon: np.ndarray, deltas: dict, historicos: dict
) -> pd.DataFrame:
    """Delta por célula (Silver), só células com dado, para rastreabilidade."""
    malha_lat, malha_lon = np.meshgrid(lat, lon, indexing="ij")
    partes = []
    for (modelo, cenario, janela), grade in deltas.items():
        valido = np.isfinite(grade)
        partes.append(
            pd.DataFrame(
                {
                    "modelo": modelo,
                    "cenario": cenario,
                    "janela": janela,
                    "lat": malha_lat[valido],
                    "lon": malha_lon[valido],
                    "rsds_historico_w_m2": historicos[modelo][valido],
                    "delta": grade[valido],
                }
            )
        )
    return pd.concat(partes, ignore_index=True)


def construir_projecao() -> tuple[pd.DataFrame, pd.DataFrame]:
    caminho_log = configurar_logging("PROJECAO_IRRADIACAO", config.PASTA_LOGS)
    pontos = pd.read_parquet(config.ARQUIVO_PONTOS)
    potencial = pd.read_parquet(config.ARQUIVO_GOLD_MUNICIPAL)
    base = potencial[COLUNAS_BASE]

    lat, lon, deltas, historicos = deltas_por_celula()
    celulas = tabela_celulas(lat, lon, deltas, historicos)
    celulas.to_parquet(config.ARQUIVO_DELTA_CELULAS, index=False)

    deltas_mun = tabela_deltas_municipais(pontos, lat, lon, deltas)
    if deltas_mun["delta"].isna().any():
        raise ValueError("Município sem delta após a associação à célula.")

    municipal = montar_municipal(base, deltas_mun)
    uf = montar_uf(base, deltas_mun)

    # Conferências: x observado reproduz a Gold; a taxa não muda com H.
    x_recalculado = energia_mwh_ano(
        base["kwp_potencial"], base["irradiacao_kwh_m2_dia"]
    )
    if not np.allclose(x_recalculado, base["x_mwh_ano"], rtol=1e-9):
        raise ValueError("x recalculado difere da Gold do potencial.")
    taxa_proj = municipal["y_projetado_mwh_ano"] / municipal["x_projetado_mwh_ano"]
    if not np.allclose(
        taxa_proj, municipal["taxa_realizacao"], rtol=1e-9, equal_nan=True
    ):
        raise ValueError("A taxa de realização mudou com a irradiação.")

    municipal.to_parquet(config.ARQUIVO_PROJECAO_MUNICIPAL, index=False)
    uf.to_parquet(config.ARQUIVO_PROJECAO_UF, index=False)

    alertas = alertas_sanidade(deltas_mun)
    logging.info(
        "Gold: %s (%d linhas) e %s (%d linhas)",
        config.ARQUIVO_PROJECAO_MUNICIPAL.name,
        len(municipal),
        config.ARQUIVO_PROJECAO_UF.name,
        len(uf),
    )
    logging.info(
        "Sanidade: %d combinações município x modelo com |delta| > %.0f%%",
        len(alertas),
        100 * config.LIMITE_ALERTA_DELTA,
    )
    distantes = municipal.drop_duplicates("cod_ibge").query("distancia_celula_km > 30")
    logging.info(
        "Municípios a mais de 30 km da célula com dado: %s",
        distantes[["cod_ibge", "uf", "distancia_celula_km"]]
        .round(1)
        .to_dict("records"),
    )
    logging.info("Log: %s", caminho_log)
    return municipal, uf


if __name__ == "__main__":
    construir_projecao()
