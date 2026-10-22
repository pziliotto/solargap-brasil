"""
PROJETO: SolarGap Brasil
ARQUIVO: rotas/noticias.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026

DESCRIÇÃO:
    GET  /noticias          lista paginada e filtrável (sem o texto completo)
    GET  /noticias/fontes   fontes do corpus, com quantidade e nível de texto
    GET  /noticias/{id}     detalhe, com texto e texto_para_modelo
    POST /noticias          envio de nova notícia (201, 409 ou 422)

PREPARAÇÃO PARA O TP4:
    - texto_para_modelo é a entrada que o LLM receberá: título + linha fina
      (+ texto, se o nível for integral), com limite de tamanho;
    - notícias enviadas por POST entram com resumo/sentimento nulos e serão
      processadas como as demais;
    - a futura rota POST /processar_texto seguirá o mesmo padrão: modelo de
      entrada validado, modelo de resposta e erros HTTP documentados.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from src.api.dependencias import RepositorioDep, registros
from src.api.modelos import (
    Erro,
    FonteResumo,
    Noticia,
    NoticiaDetalhe,
    NovaNoticia,
    PaginaNoticias,
)
from src.preparacao import esquema
from src.servicos import noticias as servico
from src.servicos.texto import texto_para_modelo

roteador = APIRouter(prefix="/noticias", tags=["Notícias"])


def _noticia(item: dict, detalhe: bool = False) -> dict:
    item = dict(item)
    item["ufs_mencionadas"] = servico.lista_ufs(item.get("ufs_mencionadas"))
    item["linha_fina"] = item.get("linha_fina") or None
    if detalhe:
        item["texto"] = item.get("texto") or None
        item["texto_para_modelo"] = texto_para_modelo(
            item["titulo"], item["linha_fina"], item["texto"], item["nivel_texto"]
        )
    return item


@roteador.get("", response_model=PaginaNoticias, summary="Lista notícias com filtros")
def listar_noticias(
    repositorio: RepositorioDep,
    fonte: Annotated[
        str | None, Query(description="Nome exato da fonte (ex.: Agência Gov).")
    ] = None,
    uf: Annotated[
        str | None, Query(min_length=2, max_length=2, description="UF mencionada.")
    ] = None,
    termo: Annotated[
        str | None,
        Query(min_length=3, description="Busca em título, linha fina e texto."),
    ] = None,
    desde: Annotated[
        date | None, Query(description="Publicadas a partir de (AAAA-MM-DD).")
    ] = None,
    ate: Annotated[
        date | None, Query(description="Publicadas até (AAAA-MM-DD), inclusive.")
    ] = None,
    nivel_texto: Annotated[str | None, Query(pattern="^(integral|metadados)$")] = None,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    deslocamento: Annotated[
        int, Query(ge=0, description="Quantas notícias pular (paginação).")
    ] = 0,
) -> PaginaNoticias:
    if desde and ate and desde > ate:
        raise HTTPException(
            status_code=400, detail="'desde' não pode ser posterior a 'ate'."
        )
    filtrado = servico.filtrar_noticias(
        repositorio.corpus, fonte, uf, termo, desde, ate, nivel_texto
    )
    filtrado = filtrado.sort_values(
        "data_publicacao", ascending=False, na_position="last"
    )
    pagina = filtrado.iloc[deslocamento : deslocamento + limite].drop(columns="texto")
    return PaginaNoticias(
        total=len(filtrado),
        limite=limite,
        deslocamento=deslocamento,
        itens=[Noticia(**_noticia(item)) for item in registros(pagina)],
    )


@roteador.get(
    "/fontes", response_model=list[FonteResumo], summary="Fontes presentes no corpus"
)
def listar_fontes(repositorio: RepositorioDep) -> list[FonteResumo]:
    resumo = repositorio.corpus.groupby("fonte").agg(
        quantidade=("id", "size"),
        niveis_texto=("nivel_texto", lambda s: sorted(s.dropna().unique().tolist())),
        mais_recente=("data_publicacao", "max"),
    )
    return [FonteResumo(**item) for item in registros(resumo.reset_index())]


@roteador.get(
    "/{id_noticia}",
    response_model=NoticiaDetalhe,
    summary="Detalhe de uma notícia",
    responses={404: {"model": Erro, "description": "Id inexistente."}},
)
def detalhar_noticia(id_noticia: str, repositorio: RepositorioDep) -> NoticiaDetalhe:
    linha = repositorio.corpus[repositorio.corpus["id"] == id_noticia]
    if linha.empty:
        raise HTTPException(
            status_code=404, detail=f"Notícia '{id_noticia}' não encontrada."
        )
    return NoticiaDetalhe(**_noticia(registros(linha)[0], detalhe=True))


@roteador.post(
    "",
    response_model=NoticiaDetalhe,
    status_code=status.HTTP_201_CREATED,
    summary="Envia uma nova notícia ao corpus",
    description=(
        "Valida os campos (URL, tamanhos, data entre 2012 e hoje), recusa URLs já existentes "
        "(409), detecta as UFs mencionadas e grava em data/external/noticias_enviadas.csv. "
        "Com texto, a notícia entra como 'integral'; sem texto, como 'metadados'."
    ),
    responses={
        409: {"model": Erro, "description": "Já existe notícia com esta URL."},
        422: {"description": "Campos inválidos (detalhados por campo)."},
    },
)
def criar_noticia(nova: NovaNoticia, repositorio: RepositorioDep) -> NoticiaDetalhe:
    try:
        registro = servico.registrar_noticia(
            fonte=nova.fonte,
            url=str(nova.url),
            titulo=nova.titulo,
            data_publicacao=nova.data_publicacao,
            linha_fina=nova.linha_fina,
            texto=nova.texto,
            corpus_atual=repositorio.corpus,
            pasta_external=repositorio.pasta_external,
        )
    except servico.NoticiaDuplicada as erro:
        raise HTTPException(status_code=409, detail=str(erro)) from erro

    repositorio.recarregar_corpus()
    registro = {**registro, "data_publicacao": registro["data_publicacao"].isoformat()}
    registro["coletado_em"] = None
    assert registro["nivel_texto"] in esquema.NIVEIS_TEXTO
    return NoticiaDetalhe(**_noticia(registro, detalhe=True))
