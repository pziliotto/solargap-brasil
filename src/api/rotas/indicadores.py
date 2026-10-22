"""
PROJETO: SolarGap Brasil
ARQUIVO: rotas/indicadores.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026

DESCRIÇÃO:
    Consulta de indicadores (GET), todos calculados por src/servicos:
        GET /ufs              indicadores das 27 UFs no recorte
        GET /ufs/{sigla}      ficha completa de uma UF
        GET /ranking          UFs ordenadas por uma métrica
        GET /series/{sigla}   série anual, parque acumulado e crescimento
        GET /oportunidades    matriz adoção x crescimento (quadrantes)

FILTROS COMUNS (query string):
    ano_inicio, ano_fim, classes (repetível), incluir_imputados

USO NO TP5:
    Estas rotas são as "ferramentas" naturais do agente inteligente: a ficha
    da UF (/ufs/{sigla}) reúne, em uma chamada, tudo o que uma recomendação
    sobre um estado precisa.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from src.api.dependencias import FiltrosDep, RepositorioDep, registros
from src.api.modelos import (
    AdesaoICMS,
    CrescimentoUF,
    DetalheUF,
    Erro,
    IndicadorUF,
    ItemOportunidade,
    ItemRanking,
    NomeMetrica,
    PontoSerie,
    RespostaIndicadores,
    RespostaOportunidades,
    RespostaRanking,
    SerieUF,
)
from src.preparacao import esquema
from src.servicos import indicadores
from src.servicos.noticias import filtrar_noticias

roteador = APIRouter(tags=["Indicadores"])

ERROS_FILTRO = {
    400: {
        "model": Erro,
        "description": "Filtros incoerentes (ex.: ano_inicio > ano_fim).",
    },
    503: {"model": Erro, "description": "Arquivos da camada Gold ausentes."},
}
SiglaPath = Annotated[
    str, Path(description="Sigla da UF (ex.: RS).", min_length=2, max_length=2)
]
AnoBase = Annotated[int, Query(description="Início da janela de crescimento.")]
AnoFinal = Annotated[
    int, Query(description="Fim da janela (último ano completo, no máximo).")
]


def _validar_sigla(sigla: str) -> str:
    sigla = sigla.upper()
    if sigla not in esquema.UFS:
        raise HTTPException(
            status_code=404,
            detail=f"UF '{sigla}' não encontrada. Use uma das 27 siglas.",
        )
    return sigla


def _indicadores(repositorio, filtros):
    return indicadores.indicadores_por_uf(
        repositorio.agregado,
        repositorio.dim_uf,
        filtros.ano_inicio,
        filtros.ano_fim,
        filtros.classes,
        filtros.incluir_imputados,
    )


@roteador.get(
    "/ufs",
    response_model=RespostaIndicadores,
    summary="Indicadores de todas as UFs",
    responses=ERROS_FILTRO,
)
def listar_ufs(repositorio: RepositorioDep, filtros: FiltrosDep) -> RespostaIndicadores:
    tabela = _indicadores(repositorio, filtros).sort_values("sigla_uf")
    return RespostaIndicadores(
        filtros=filtros.como_dict(),
        media_brasil=indicadores.media_brasil(tabela),
        itens=registros(tabela.drop(columns="potencia_kw")),
    )


@roteador.get(
    "/ufs/{sigla}",
    response_model=DetalheUF,
    summary="Ficha completa de uma UF",
    description=(
        "Indicadores no recorte, posição nas quatro métricas, crescimento do parque "
        "(CAGR na janela informada), quadrante de oportunidade, adesão ao ICMS e número "
        "de notícias que mencionam a UF."
    ),
    responses={
        404: {"model": Erro, "description": "Sigla inexistente."},
        **ERROS_FILTRO,
    },
)
def detalhar_uf(
    sigla: SiglaPath,
    repositorio: RepositorioDep,
    filtros: FiltrosDep,
    ano_base: AnoBase = indicadores.ANO_BASE_CRESCIMENTO,
    ano_final: AnoFinal = indicadores.ANO_FINAL_CRESCIMENTO,
) -> DetalheUF:
    sigla = _validar_sigla(sigla)
    tabela = _indicadores(repositorio, filtros)
    crescimento, cagr_brasil = indicadores.taxa_crescimento(
        repositorio.agregado,
        filtros.classes,
        filtros.incluir_imputados,
        ano_base,
        ano_final,
    )
    matriz, _ = indicadores.matriz_oportunidade(tabela, crescimento, cagr_brasil)

    linha_uf = registros(
        tabela[tabela["sigla_uf"] == sigla].drop(columns="potencia_kw")
    )[0]
    linha_cresc = registros(crescimento[crescimento["sigla_uf"] == sigla])[0]

    icms = None
    if repositorio.icms is not None:
        adesao = repositorio.icms[repositorio.icms["sigla_uf"] == sigla]
        if not adesao.empty:
            icms = AdesaoICMS(**registros(adesao)[0])

    return DetalheUF(
        filtros=filtros.como_dict(),
        indicadores=IndicadorUF(**linha_uf),
        posicoes=indicadores.posicoes(tabela, sigla),
        media_brasil=indicadores.media_brasil(tabela),
        crescimento=CrescimentoUF(**linha_cresc, cagr_brasil_pct=cagr_brasil),
        quadrante=matriz.set_index("sigla_uf").loc[sigla, "quadrante"],
        icms=icms,
        noticias_relacionadas=len(filtrar_noticias(repositorio.corpus, uf=sigla)),
    )


@roteador.get(
    "/ranking",
    response_model=RespostaRanking,
    summary="Ranking das UFs por uma métrica",
    responses=ERROS_FILTRO,
)
def obter_ranking(
    repositorio: RepositorioDep,
    filtros: FiltrosDep,
    metrica: Annotated[
        NomeMetrica, Query(description="Métrica do ranking.")
    ] = NomeMetrica.watts_por_habitante,
    ordem: Annotated[
        str, Query(pattern="^(desc|asc)$", description="desc: maiores primeiro.")
    ] = "desc",
    limite: Annotated[
        int, Query(ge=1, le=27, description="Quantas UFs devolver.")
    ] = 27,
) -> RespostaRanking:
    tabela = _indicadores(repositorio, filtros)
    ordenado = indicadores.ranking(
        tabela, metrica.value, ascendente=(ordem == "asc"), limite=limite
    )
    ordenado = ordenado.assign(valor=ordenado[metrica.value])
    info = indicadores.METRICAS[metrica.value]
    return RespostaRanking(
        metrica=metrica,
        rotulo=info.rotulo,
        unidade=info.unidade,
        ordem=ordem,
        filtros=filtros.como_dict(),
        media_brasil=indicadores.media_brasil(tabela)[metrica.value]
        if info.per_capita
        else None,
        itens=[
            ItemRanking(**item)
            for item in registros(ordenado.drop(columns="potencia_kw"))
        ],
    )


@roteador.get(
    "/series/{sigla}",
    response_model=SerieUF,
    summary="Série anual e crescimento do parque de uma UF",
    responses={
        404: {"model": Erro, "description": "Sigla inexistente."},
        **ERROS_FILTRO,
    },
)
def serie_uf(
    sigla: SiglaPath, repositorio: RepositorioDep, filtros: FiltrosDep
) -> SerieUF:
    sigla = _validar_sigla(sigla)
    serie = indicadores.serie_acumulada(
        repositorio.agregado, filtros.classes, filtros.incluir_imputados
    )
    serie = serie[
        (serie["sigla_uf"] == sigla)
        & serie["ano"].between(filtros.ano_inicio, filtros.ano_fim)
    ]
    return SerieUF(
        sigla_uf=sigla,
        nome_uf=esquema.UFS[sigla][1],
        filtros=filtros.como_dict(),
        pontos=[PontoSerie(**p) for p in registros(serie.drop(columns="sigla_uf"))],
    )


@roteador.get(
    "/oportunidades",
    response_model=RespostaOportunidades,
    summary="Matriz de oportunidade: adoção x crescimento",
    description=(
        "Adoção = W/hab acumulado até o fim do recorte; crescimento = CAGR do parque na janela "
        "ano_base-ano_final. Referências: média nacional (total/população) e CAGR do Brasil."
    ),
    responses=ERROS_FILTRO,
)
def oportunidades(
    repositorio: RepositorioDep,
    filtros: FiltrosDep,
    ano_base: AnoBase = indicadores.ANO_BASE_CRESCIMENTO,
    ano_final: AnoFinal = indicadores.ANO_FINAL_CRESCIMENTO,
) -> RespostaOportunidades:
    tabela = _indicadores(repositorio, filtros)
    crescimento, cagr_brasil = indicadores.taxa_crescimento(
        repositorio.agregado,
        filtros.classes,
        filtros.incluir_imputados,
        ano_base,
        ano_final,
    )
    matriz, referencia = indicadores.matriz_oportunidade(
        tabela, crescimento, cagr_brasil
    )
    janela = crescimento.iloc[0]
    return RespostaOportunidades(
        ano_base=int(janela["ano_base"]),
        ano_final=int(janela["ano_final"]),
        referencia=referencia,
        quadrantes=indicadores.DESCRICAO_QUADRANTES,
        itens=[ItemOportunidade(**item) for item in registros(matriz)],
    )
