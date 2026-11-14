"""
PROJETO: SolarGap Brasil
ARQUIVO: indicadores.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Cálculo dos indicadores do projeto a partir da camada Gold. Funções puras:
    recebem DataFrames e parâmetros simples, devolvem DataFrames novos.

ORIGEM:
    filtrar, indicadores_por_uf e serie_anual vieram de src/app/carregamento.py
    (TP2), sem mudança de regra. O que é novo no TP3:
        - validar_filtros: mensagens de erro reutilizadas pela API (HTTP 400);
        - serie_acumulada e taxa_crescimento: KPI "Taxa de crescimento anual",
          que no TP2 estava parcial (só havia a série anual);
        - matriz_oportunidade: cruza adoção per capita e crescimento e
          classifica cada UF em um quadrante — a resposta direta à pergunta
          do projeto, "onde está o próximo mercado solar?".

DEFINIÇÕES:
    Watts por habitante ............ potência (kW) x 1.000 / população (Censo 2022)
    Empreendimentos por 100 mil hab. qtd / população x 100.000
    Potência acumulada ............. soma da potência conectada até o fim do ano,
                                     reconstruída a partir do ano de conexão
                                     (a base da ANEEL é um retrato dos ativos)
    Crescimento anual (%) .......... acumulado(t) / acumulado(t-1) - 1
    CAGR da janela (%) ............. (acum. final / acum. base) ^ (1 / anos) - 1

POR QUE O CRESCIMENTO USA O ESTOQUE, E NÃO O FLUXO:
    O KPI do Charter é a variação da POTÊNCIA INSTALADA. A potência adicionada
    no ano (fluxo) caiu em 2023 por efeito regulatório (fim da isenção do Fio B),
    mas o parque instalado continuou crescendo. Medir o estoque evita confundir
    "desaceleração das novas conexões" com "retração do mercado".

POR QUE A JANELA PADRÃO É 2022-2025:
    2022 é o ano da Lei 14.300 (Marco Legal da GD), recorte central do projeto;
    2025 é o último ano completo (2026 é parcial). Janelas longas a partir de
    2012 produzem taxas sem significado: estados com base quase nula no início
    exibem crescimentos de milhares de por cento.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.preparacao import esquema

# ═══════════════════ Catálogo de métricas ═══════════════════


@dataclass(frozen=True)
class Metrica:
    rotulo: str
    unidade: str
    casas: int
    per_capita: bool

    @property
    def rotulo_frase(self) -> str:
        """Rótulo para o meio de uma frase: só a inicial em minúscula ("(MW)" fica intacto)."""
        return self.rotulo[0].lower() + self.rotulo[1:]


METRICAS: dict[str, Metrica] = {
    "watts_por_habitante": Metrica("Watts por habitante", "W/hab", 1, True),
    "empreendimentos_por_100k_hab": Metrica(
        "Empreendimentos por 100 mil hab.", "por 100 mil hab.", 1, True
    ),
    "potencia_mw": Metrica("Potência instalada (MW)", "MW", 1, False),
    "qtd_empreendimentos": Metrica(
        "Número de empreendimentos", "empreendimentos", 0, False
    ),
}

ANO_BASE_CRESCIMENTO = 2022  # Lei 14.300/2022
ANO_FINAL_CRESCIMENTO = esquema.ANO_PARCIAL - 1  # último ano completo

QUADRANTES = {
    (True, True): "Líder em expansão",
    (True, False): "Mercado maduro",
    (False, True): "Mercado emergente",
    (False, False): "Lacuna persistente",
}
DESCRICAO_QUADRANTES = {
    "Líder em expansão": "Adoção e crescimento acima da referência nacional.",
    "Mercado maduro": "Adoção acima da referência, crescimento abaixo: base já instalada.",
    "Mercado emergente": "Adoção abaixo da referência, crescimento acima: o próximo mercado.",
    "Lacuna persistente": "Adoção e crescimento abaixo da referência: foco de política pública.",
}


class FiltroInvalido(ValueError):
    """Combinação de filtros sem sentido (ex.: ano inicial maior que o final)."""


# ═══════════════════ Filtros ═══════════════════


def anos_disponiveis(agregado: pd.DataFrame) -> tuple[int, int]:
    return int(agregado["ano"].min()), int(agregado["ano"].max())


def classes_disponiveis(agregado: pd.DataFrame) -> list[str]:
    return sorted(agregado["classe_consumo"].dropna().unique().tolist())


def validar_filtros(
    agregado: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
    classes: tuple[str, ...] | None,
) -> tuple[str, ...]:
    """Valida o recorte e devolve a tupla de classes efetiva (todas, se None)."""
    ano_min, ano_max = anos_disponiveis(agregado)
    if ano_inicio > ano_fim:
        raise FiltroInvalido(
            f"ano_inicio ({ano_inicio}) maior que ano_fim ({ano_fim})."
        )
    if ano_fim < ano_min or ano_inicio > ano_max:
        raise FiltroInvalido(
            f"Período fora da base: os dados vão de {ano_min} a {ano_max}."
        )

    todas = classes_disponiveis(agregado)
    if not classes:
        return tuple(todas)

    desconhecidas = sorted(set(classes) - set(todas))
    if desconhecidas:
        raise FiltroInvalido(
            f"Classes de consumo desconhecidas: {desconhecidas}. Válidas: {todas}."
        )
    return tuple(classes)


def filtrar(
    agregado: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
    classes: tuple[str, ...],
    incluir_imputados: bool,
) -> pd.DataFrame:
    filtro = agregado["ano"].between(ano_inicio, ano_fim) & agregado[
        "classe_consumo"
    ].isin(classes)
    if not incluir_imputados:
        filtro &= ~agregado["fonte_imputada"]
    return agregado[filtro]


# ═══════════════════ Indicadores por UF ═══════════════════


def indicadores_por_uf(
    agregado: pd.DataFrame,
    dim_uf: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
    classes: tuple[str, ...],
    incluir_imputados: bool,
) -> pd.DataFrame:
    """Soma o agregado filtrado por UF e recalcula os indicadores per capita."""
    filtrado = filtrar(agregado, ano_inicio, ano_fim, classes, incluir_imputados)
    filtrado = filtrado.assign(
        qtd_imputados=filtrado["qtd_empreendimentos"].where(
            filtrado["fonte_imputada"], 0
        )
    )
    totais = filtrado.groupby("sigla_uf", as_index=False).agg(
        potencia_kw=("potencia_kw", "sum"),
        qtd_empreendimentos=("qtd_empreendimentos", "sum"),
        qtd_imputados=("qtd_imputados", "sum"),
    )

    base = dim_uf[["sigla_uf", "nome_uf", "regiao", "populacao"]].merge(
        totais, on="sigla_uf", how="left"
    )
    medidas = ["potencia_kw", "qtd_empreendimentos", "qtd_imputados"]
    base[medidas] = base[medidas].fillna(0)
    base["qtd_empreendimentos"] = base["qtd_empreendimentos"].astype(int)
    base["qtd_imputados"] = base["qtd_imputados"].astype(int)

    base["potencia_mw"] = base["potencia_kw"] / 1_000
    base["watts_por_habitante"] = base["potencia_kw"] * 1_000 / base["populacao"]
    base["empreendimentos_por_100k_hab"] = (
        base["qtd_empreendimentos"] / base["populacao"] * 100_000
    )
    return base


def media_brasil(indicadores: pd.DataFrame) -> dict[str, float]:
    """Referência nacional: total do país dividido pela população do país.

    Não é a média simples das UFs — essa daria o mesmo peso a SP e a RR.
    """
    populacao = indicadores["populacao"].sum()
    return {
        "watts_por_habitante": indicadores["potencia_kw"].sum() * 1_000 / populacao,
        "empreendimentos_por_100k_hab": indicadores["qtd_empreendimentos"].sum()
        / populacao
        * 100_000,
    }


def ranking(
    indicadores: pd.DataFrame,
    metrica: str,
    ascendente: bool = False,
    limite: int | None = None,
) -> pd.DataFrame:
    """Ordena as UFs pela métrica. A coluna posicao é sempre 1 = maior valor."""
    if metrica not in METRICAS:
        raise FiltroInvalido(f"Métrica desconhecida: {metrica}. Use {list(METRICAS)}.")

    ordenado = indicadores.sort_values(metrica, ascending=False).reset_index(drop=True)
    ordenado.insert(0, "posicao", range(1, len(ordenado) + 1))
    if ascendente:
        ordenado = ordenado.iloc[::-1].reset_index(drop=True)
    return ordenado.head(limite) if limite else ordenado


def posicoes(indicadores: pd.DataFrame, sigla: str) -> dict[str, int]:
    """Posição da UF (1 = maior) em cada métrica do catálogo."""
    resultado = {}
    for metrica in METRICAS:
        ordem = indicadores.sort_values(metrica, ascending=False)["sigla_uf"].tolist()
        resultado[metrica] = ordem.index(sigla) + 1
    return resultado


# ═══════════════════ Séries ═══════════════════


def serie_anual(
    agregado: pd.DataFrame,
    ano_inicio: int,
    ano_fim: int,
    classes: tuple[str, ...],
    incluir_imputados: bool,
) -> pd.DataFrame:
    """Potência (MW) e empreendimentos conectados por UF e ano, já filtrados."""
    filtrado = filtrar(agregado, ano_inicio, ano_fim, classes, incluir_imputados)
    serie = filtrado.groupby(["sigla_uf", "ano"], as_index=False).agg(
        potencia_kw=("potencia_kw", "sum"),
        qtd_empreendimentos=("qtd_empreendimentos", "sum"),
    )
    serie["potencia_mw"] = serie["potencia_kw"] / 1_000
    return serie


def serie_acumulada(
    agregado: pd.DataFrame,
    classes: tuple[str, ...],
    incluir_imputados: bool,
) -> pd.DataFrame:
    """Estoque de potência por UF ao fim de cada ano, com crescimento anual.

    Usa SEMPRE o histórico completo, ignorando o filtro de período: o estoque de
    2024 depende de tudo o que foi conectado antes. Quem chama recorta os anos
    para exibição depois do cálculo.

    A grade UF x ano é completa: anos sem novas conexões entram com zero, para
    que o acumulado seja carregado adiante corretamente.
    """
    ano_min, ano_max = anos_disponiveis(agregado)
    filtrado = filtrar(agregado, ano_min, ano_max, classes, incluir_imputados)
    anual = filtrado.groupby(["sigla_uf", "ano"]).agg(
        potencia_kw=("potencia_kw", "sum"),
        qtd_empreendimentos=("qtd_empreendimentos", "sum"),
    )

    grade = pd.MultiIndex.from_product(
        [sorted(esquema.UFS), range(ano_min, ano_max + 1)], names=["sigla_uf", "ano"]
    )
    serie = anual.reindex(grade, fill_value=0).reset_index()
    serie = serie.sort_values(["sigla_uf", "ano"])

    serie["potencia_mw"] = serie["potencia_kw"] / 1_000
    por_uf = serie.groupby("sigla_uf")
    serie["potencia_acumulada_mw"] = por_uf["potencia_mw"].cumsum()
    serie["qtd_acumulada"] = por_uf["qtd_empreendimentos"].cumsum()

    anterior = serie.groupby("sigla_uf")["potencia_acumulada_mw"].shift(1)
    serie["crescimento_pct"] = np.where(
        anterior > 0, (serie["potencia_acumulada_mw"] / anterior - 1) * 100, np.nan
    )
    serie["ano_parcial"] = serie["ano"] == esquema.ANO_PARCIAL
    return serie.drop(columns="potencia_kw").reset_index(drop=True)


def _cagr(base: pd.Series | float, final: pd.Series | float, anos: int):
    base_arr = np.asarray(base, dtype=float)
    final_arr = np.asarray(final, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        taxa = (np.power(final_arr / base_arr, 1 / anos) - 1) * 100
    return np.where(base_arr > 0, taxa, np.nan)


def ajustar_janela(ano_base: int, ano_final: int) -> tuple[int, int]:
    """Restringe a janela de crescimento a anos completos e com ao menos 1 ano."""
    ano_final = min(ano_final, ANO_FINAL_CRESCIMENTO)
    ano_base = max(ano_base, esquema.ANO_MINIMO)
    if ano_base >= ano_final:
        raise FiltroInvalido(
            f"Janela de crescimento inválida ({ano_base}-{ano_final}): o ano base deve "
            f"ser anterior ao final, e o final no máximo {ANO_FINAL_CRESCIMENTO} "
            f"({esquema.ANO_PARCIAL} é parcial)."
        )
    return ano_base, ano_final


def taxa_crescimento(
    agregado: pd.DataFrame,
    classes: tuple[str, ...],
    incluir_imputados: bool,
    ano_base: int = ANO_BASE_CRESCIMENTO,
    ano_final: int = ANO_FINAL_CRESCIMENTO,
) -> tuple[pd.DataFrame, float]:
    """CAGR do estoque de potência por UF e a referência nacional.

    Devolve (tabela por UF, CAGR do Brasil em %).
    """
    ano_base, ano_final = ajustar_janela(ano_base, ano_final)
    anos = ano_final - ano_base

    serie = serie_acumulada(agregado, classes, incluir_imputados)
    estoque = serie.pivot(
        index="sigla_uf", columns="ano", values="potencia_acumulada_mw"
    )

    tabela = pd.DataFrame(
        {
            "sigla_uf": estoque.index,
            "ano_base": ano_base,
            "ano_final": ano_final,
            "acumulado_base_mw": estoque[ano_base].to_numpy(),
            "acumulado_final_mw": estoque[ano_final].to_numpy(),
        }
    )
    tabela["cagr_pct"] = _cagr(
        tabela["acumulado_base_mw"], tabela["acumulado_final_mw"], anos
    )

    brasil = float(_cagr(estoque[ano_base].sum(), estoque[ano_final].sum(), anos))
    return tabela.reset_index(drop=True), brasil


# ═══════════════════ Oportunidades ═══════════════════


def matriz_oportunidade(
    indicadores: pd.DataFrame,
    crescimento: pd.DataFrame,
    cagr_brasil: float,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Classifica cada UF por adoção per capita x crescimento do estoque.

    Referências: a média nacional de W/hab (total/população) e o CAGR do país.
    Devolve (tabela com quadrante, referências usadas).
    """
    referencia = {
        "watts_por_habitante": media_brasil(indicadores)["watts_por_habitante"],
        "cagr_pct": cagr_brasil,
    }

    matriz = indicadores[
        ["sigla_uf", "nome_uf", "regiao", "watts_por_habitante", "potencia_mw"]
    ].merge(crescimento[["sigla_uf", "cagr_pct"]], on="sigla_uf", how="left")

    adocao_alta = matriz["watts_por_habitante"] >= referencia["watts_por_habitante"]
    crescimento_alto = matriz["cagr_pct"] >= referencia["cagr_pct"]
    matriz["quadrante"] = [
        QUADRANTES[(bool(a), bool(c))]
        for a, c in zip(adocao_alta, crescimento_alto, strict=True)
    ]
    return matriz.sort_values("cagr_pct", ascending=False).reset_index(
        drop=True
    ), referencia


def correlacao_spearman(x: pd.Series, y: pd.Series) -> float | None:
    """Correlação de postos (Spearman) sem depender do scipy.

    Spearman = Pearson aplicado aos postos. Robusta a valores extremos (como as
    taxas altas de UFs com base pequena) e não supõe relação linear.
    Devolve None com menos de 3 pares válidos.
    """
    pares = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(pares) < 3:
        return None
    return float(pares["x"].rank().corr(pares["y"].rank()))
