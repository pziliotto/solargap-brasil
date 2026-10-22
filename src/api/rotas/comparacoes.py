"""
PROJETO: SolarGap Brasil
ARQUIVO: rotas/comparacoes.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026

DESCRIÇÃO:
    POST /comparacoes — recebe um indicador próprio por UF (carteira de
    clientes, instaladores, metas) e devolve a comparação com a adoção de
    energia solar: posições, diferença de posições e correlação de Spearman.

    É a versão em API do upload da página Dados: o mesmo caso de uso, agora
    acessível a outros sistemas (ex.: o CRM de uma empresa do setor).
"""

from fastapi import APIRouter

from src.api.dependencias import RepositorioDep, registros
from src.api.modelos import Erro, ItemComparacao, PedidoComparacao, RespostaComparacao
from src.servicos import indicadores

roteador = APIRouter(tags=["Comparações"])


def _interpretar(rho: float | None) -> str:
    if rho is None:
        return "Pares insuficientes para calcular a correlação."
    forca = "forte" if abs(rho) >= 0.7 else "moderada" if abs(rho) >= 0.4 else "fraca"
    sentido = "positiva" if rho > 0 else "negativa"
    return (
        f"Correlação {sentido} {forca} ({rho:.2f}). UFs com diferenca_posicoes positiva têm "
        "presença do indicador abaixo do que a adoção sugere: candidatas a mercado pouco explorado."
    )


@roteador.post(
    "/comparacoes",
    response_model=RespostaComparacao,
    summary="Compara um indicador próprio com a adoção de energia solar",
    responses={
        400: {"model": Erro, "description": "Filtros incoerentes."},
        422: {"description": "UF inválida, menos de 3 UFs ou valor não numérico."},
    },
)
def comparar(
    pedido: PedidoComparacao, repositorio: RepositorioDep
) -> RespostaComparacao:
    ano_min, ano_max = indicadores.anos_disponiveis(repositorio.agregado)
    inicio = pedido.ano_inicio or ano_min
    fim = pedido.ano_fim or ano_max
    classes = indicadores.validar_filtros(repositorio.agregado, inicio, fim, None)
    tabela = indicadores.indicadores_por_uf(
        repositorio.agregado,
        repositorio.dim_uf,
        inicio,
        fim,
        classes,
        pedido.incluir_imputados,
    )

    metrica = pedido.metrica.value
    base = tabela[tabela["sigla_uf"].isin(pedido.valores)].copy()
    base["valor_usuario"] = base["sigla_uf"].map(pedido.valores)
    base["valor_metrica"] = base[metrica]
    base["posicao_usuario"] = (
        base["valor_usuario"].rank(ascending=False, method="min").astype(int)
    )
    base["posicao_metrica"] = (
        base["valor_metrica"].rank(ascending=False, method="min").astype(int)
    )
    base["diferenca_posicoes"] = base["posicao_usuario"] - base["posicao_metrica"]
    rho = indicadores.correlacao_spearman(base["valor_usuario"], base["valor_metrica"])

    colunas = list(ItemComparacao.model_fields)
    return RespostaComparacao(
        nome_indicador=pedido.nome_indicador,
        metrica=pedido.metrica,
        filtros={
            "ano_inicio": inicio,
            "ano_fim": fim,
            "classes": list(classes),
            "incluir_imputados": pedido.incluir_imputados,
        },
        n_ufs=len(base),
        correlacao_spearman=rho,
        interpretacao=_interpretar(rho),
        itens=[
            ItemComparacao(**item)
            for item in registros(
                base.sort_values("diferenca_posicoes", ascending=False)[colunas]
            )
        ],
    )


_ = Erro  # usado na documentação de respostas
