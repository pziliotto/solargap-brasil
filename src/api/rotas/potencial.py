"""
PROJETO: SolarGap Brasil
ARQUIVO: rotas/potencial.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026

DESCRIÇÃO:
    Potencial solar residencial municipal (TP4.5, Tarefa 7), calculado por
    src/servicos/potencial.py, o mesmo código da página "Potencial Solar":
        GET /potencial/uf                       x, y, gap e taxa das 27 UFs e do Brasil
        GET /potencial/municipio/{cod_ibge}     ficha de um município
        GET /potencial/explicacao/{cod_ibge}    fatores associados à taxa (SHAP)
        GET /potencial/cenarios/{cod_ibge}      projeção da irradiação 2030–2050

PARÂMETRO COMUM:
    visao = corrigida (padrão) | aneel | conservadora. Fora da lista: 422.

ERROS:
    404  código IBGE inexistente
    422  visão inválida (validação do enum NomeVisao)
    503  Gold de potencial ausente (DadosIndisponiveis, tratado em main.py)
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from src.api.dependencias import RepositorioDep, registros
from src.api.modelos import (
    CenariosMunicipio,
    Erro,
    ExplicacaoPotencial,
    NomeVisao,
    PotencialMunicipio,
    RespostaPotencialUF,
)
from src.servicos import potencial
from src.servicos.indicadores import VISOES

roteador = APIRouter(prefix="/potencial", tags=["Potencial solar"])

ERRO_503 = {503: {"model": Erro, "description": "Gold de potencial ausente."}}
ERROS_MUNICIPIO = {
    404: {"model": Erro, "description": "Código IBGE inexistente."},
    422: {"description": "Visão inválida."},
    **ERRO_503,
}
VisaoQuery = Annotated[
    NomeVisao,
    Query(
        description=(
            "Visão da base ANEEL 10/2026: corrigida (padrão; 75 kW da COPEL-DIS imputados "
            "e 156 registros sem fonte contados como solares), aneel (dado oficial) ou "
            "conservadora (corrige só os residenciais de 75 kW)."
        )
    ),
]
CodigoPath = Annotated[
    str, Path(description="Código IBGE do município, 7 dígitos (ex.: 4305108).")
]


def _recorte(funcao, *args, **kwargs):
    """Chama o serviço e traduz RecorteInexistente em 404."""
    try:
        return funcao(*args, **kwargs)
    except potencial.RecorteInexistente as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro


@roteador.get(
    "/uf",
    response_model=RespostaPotencialUF,
    summary="Potencial, produção, gap e taxa de realização por UF",
    description=(
        "Potencial técnico residencial (x), produção estimada da MMGD residencial e rural "
        "(y), gap (x − y) e taxa de realização (y / x) das 27 UFs e do Brasil, com os três "
        "fatores de maior contribuição SHAP em cada UF."
    ),
    responses={422: {"description": "Visão inválida."}, **ERRO_503},
)
def listar_uf(
    repositorio: RepositorioDep, visao: VisaoQuery = NomeVisao.corrigida
) -> RespostaPotencialUF:
    base = repositorio.base_potencial()
    tabela = potencial.tabela_uf(base, visao.value)
    itens = [
        {**linha, "nivel": "uf", "nome": linha["uf"], "visao": visao.value}
        for linha in registros(tabela)
    ]
    return RespostaPotencialUF(
        visao=visao,
        premissas=potencial.PREMISSAS,
        brasil=potencial.resumo_recorte(base, visao.value),
        itens=itens,
    )


@roteador.get(
    "/municipio/{cod_ibge}",
    response_model=PotencialMunicipio,
    summary="Ficha de potencial de um município",
    responses=ERROS_MUNICIPIO,
)
def detalhar_municipio(
    cod_ibge: CodigoPath,
    repositorio: RepositorioDep,
    visao: VisaoQuery = NomeVisao.corrigida,
) -> PotencialMunicipio:
    base = repositorio.base_potencial()
    resumo = _recorte(potencial.resumo_recorte, base, visao.value, cod_ibge=cod_ibge)
    linha = potencial.linha_municipio(base, cod_ibge)
    taxas = {v: float(linha[potencial.COLUNAS_VISAO[v]["taxa"]]) for v in VISOES}
    return PotencialMunicipio(
        **resumo, cod_ibge=linha["cod_ibge"], uf=linha["uf"], taxas_por_visao=taxas
    )


@roteador.get(
    "/explicacao/{cod_ibge}",
    response_model=ExplicacaoPotencial,
    summary="Fatores associados à taxa de realização (SHAP)",
    description=(
        "Contribuição de cada fator para a taxa de realização prevista pelo modelo, do "
        "maior para o menor efeito, em pontos percentuais e em linguagem simples. "
        "Associação, não causalidade. O modelo foi treinado na visão corrigida; nas "
        "outras visões, a resposta traz a taxa observada da visão e o ranking global do "
        "modelo ajustado a ela."
    ),
    responses=ERROS_MUNICIPIO,
)
def explicar_municipio(
    cod_ibge: CodigoPath,
    repositorio: RepositorioDep,
    visao: VisaoQuery = NomeVisao.corrigida,
) -> ExplicacaoPotencial:
    base = repositorio.base_potencial()
    return ExplicacaoPotencial(
        **_recorte(potencial.explicar, base, visao.value, cod_ibge=cod_ibge)
    )


@roteador.get(
    "/cenarios/{cod_ibge}",
    response_model=CenariosMunicipio,
    summary="Cenários de irradiação 2030–2050 (NEX-GDDP-CMIP6)",
    description=(
        "Irradiação, potencial (x), produção (y) e gap projetados em SSP2-4.5 e SSP5-8.5, "
        "nas janelas 2030–2039 e 2040–2050, com a mediana e a faixa (mín.–máx.) de 5 "
        "modelos climáticos. Potência instalada fixa no valor atual. É um cenário com "
        "faixa de incerteza, não uma previsão."
    ),
    responses=ERROS_MUNICIPIO,
)
def cenarios_municipio(
    cod_ibge: CodigoPath,
    repositorio: RepositorioDep,
    visao: VisaoQuery = NomeVisao.corrigida,
) -> CenariosMunicipio:
    base = repositorio.base_potencial()
    tabela = _recorte(potencial.cenarios_municipio, base, cod_ibge, visao.value)
    linha = potencial.linha_municipio(base, cod_ibge)
    return CenariosMunicipio(
        cod_ibge=linha["cod_ibge"],
        nome=linha["nome"],
        uf=linha["uf"],
        visao=visao,
        distancia_celula_km=float(tabela["distancia_celula_km"].iloc[0]),
        aviso=potencial.AVISO_CENARIOS,
        itens=registros(tabela.drop(columns="distancia_celula_km")),
    )
