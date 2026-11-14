"""
PROJETO: SolarGap Brasil
ARQUIVO: dependencias.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Dependências injetadas nas rotas (sistema Depends da FastAPI):
        - obter_repositorio: os DataFrames da Gold, lidos uma única vez;
        - obter_filtros: parâmetros de recorte comuns a várias rotas,
          já validados (ano, classe, inclusão de imputados).

CARGA ÚNICA:
    O repositório é criado no startup da aplicação (lifespan, em main.py) e
    guardado em app.state. Ler os CSVs a cada requisição seria desperdício:
    a Gold só muda quando o pipeline roda de novo. A exceção é o corpus, que
    é recarregado depois de cada POST /noticias.

TESTES:
    Os testes substituem obter_repositorio por um repositório apontando para
    pastas temporárias (app.dependency_overrides), sem tocar nos dados reais.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import Depends, Query, Request

from src.servicos import dados, indicadores


@dataclass
class Repositorio:
    agregado: pd.DataFrame
    dim_uf: pd.DataFrame
    corpus: pd.DataFrame
    icms: pd.DataFrame | None
    pasta_processed: Path = dados.PASTA_PROCESSED
    pasta_external: Path = dados.PASTA_EXTERNAL
    carregado_em: datetime = field(
        default_factory=lambda: datetime.now().replace(microsecond=0)
    )

    @classmethod
    def carregar(
        cls,
        pasta_processed: Path = dados.PASTA_PROCESSED,
        pasta_external: Path = dados.PASTA_EXTERNAL,
    ) -> Repositorio:
        """Lê a Gold. Levanta DadosIndisponiveis se faltar arquivo obrigatório."""
        return cls(
            agregado=dados.carregar_agregado(pasta_processed),
            dim_uf=dados.carregar_uf(pasta_processed),
            corpus=dados.carregar_corpus_completo(pasta_processed, pasta_external),
            icms=dados.carregar_icms(pasta_processed),
            pasta_processed=pasta_processed,
            pasta_external=pasta_external,
        )

    def recarregar_corpus(self) -> None:
        self.corpus = dados.carregar_corpus_completo(
            self.pasta_processed, self.pasta_external
        )


def obter_repositorio(request: Request) -> Repositorio:
    """Repositório carregado no startup; carrega sob demanda se ainda não existir."""
    repositorio = getattr(request.app.state, "repositorio", None)
    if repositorio is None:
        repositorio = Repositorio.carregar()  # DadosIndisponiveis -> 503 (main.py)
        request.app.state.repositorio = repositorio
    return repositorio


RepositorioDep = Annotated[Repositorio, Depends(obter_repositorio)]


@dataclass(frozen=True)
class FiltroAPI:
    ano_inicio: int
    ano_fim: int
    classes: tuple[str, ...]
    incluir_imputados: bool

    def como_dict(self) -> dict:
        return {
            "ano_inicio": self.ano_inicio,
            "ano_fim": self.ano_fim,
            "classes": list(self.classes),
            "incluir_imputados": self.incluir_imputados,
        }


def obter_filtros(
    repositorio: RepositorioDep,
    ano_inicio: Annotated[
        int | None,
        Query(description="Primeiro ano de conexão. Padrão: início da base."),
    ] = None,
    ano_fim: Annotated[
        int | None,
        Query(
            description="Último ano de conexão. Padrão: fim da base (2026 é parcial)."
        ),
    ] = None,
    classes: Annotated[
        list[str] | None,
        Query(description="Classes de consumo (repita o parâmetro). Padrão: todas."),
    ] = None,
    incluir_imputados: Annotated[
        bool,
        Query(
            description="Contar os registros sem fonte do MA como solares (visão corrigida)."
        ),
    ] = True,
) -> FiltroAPI:
    ano_min, ano_max = indicadores.anos_disponiveis(repositorio.agregado)
    inicio = ano_min if ano_inicio is None else ano_inicio
    fim = ano_max if ano_fim is None else ano_fim
    classes_validas = indicadores.validar_filtros(
        repositorio.agregado, inicio, fim, tuple(classes) if classes else None
    )  # FiltroInvalido -> 400 (main.py)
    return FiltroAPI(inicio, fim, classes_validas, incluir_imputados)


FiltrosDep = Annotated[FiltroAPI, Depends(obter_filtros)]


def registros(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> lista de dicts com tipos nativos do Python (NaN/NaT -> None).

    Passar pelo JSON do pandas evita tipos do numpy (int64, float64, Timestamp)
    na validação do Pydantic e converte datas para ISO 8601.
    """
    import json

    return json.loads(
        df.to_json(orient="records", date_format="iso", force_ascii=False)
    )
