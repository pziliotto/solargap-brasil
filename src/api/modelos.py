"""
PROJETO: SolarGap Brasil
ARQUIVO: modelos.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Modelos Pydantic da API: o contrato de cada entrada (POST) e de cada
    resposta. A FastAPI usa esses modelos para três coisas:
        1. validar o que chega — erro 422 com a lista de campos inválidos;
        2. filtrar e converter o que sai (response_model) — a resposta nunca
           vaza colunas internas nem tipos do numpy/pandas;
        3. gerar a documentação OpenAPI (/docs) com descrições e exemplos.

ANTECIPAÇÃO DO TP4:
    O TP4 pede "Response Models" e validação das respostas. Eles já nascem
    aqui. Os campos resumo e sentimento das notícias existem desde já (nulos)
    e a rota de detalhe devolve texto_para_modelo — a entrada exata que o
    modelo de linguagem receberá.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from src.preparacao import esquema

DATA_MINIMA_NOTICIA = date(esquema.ANO_MINIMO, 1, 1)


class NomeMetrica(StrEnum):
    """Métricas disponíveis para ranking e comparação."""

    watts_por_habitante = "watts_por_habitante"
    empreendimentos_por_100k_hab = "empreendimentos_por_100k_hab"
    potencia_mw = "potencia_mw"
    qtd_empreendimentos = "qtd_empreendimentos"


class Erro(BaseModel):
    detail: str = Field(description="Mensagem explicativa do erro.")


# ═══════════════════ Sistema ═══════════════════


class ResumoDados(BaseModel):
    ufs: int
    linhas_agregado: int
    noticias: int
    icms: bool = Field(
        description="Se a tabela de adesão ao ICMS 16/15 está disponível."
    )
    periodo: str = Field(description="Primeiro e último ano de conexão na base.")


class Saude(BaseModel):
    status: Literal["ok"]
    versao: str
    carregado_em: datetime = Field(description="Quando a API leu os arquivos da Gold.")
    dados: ResumoDados


# ═══════════════════ Indicadores ═══════════════════


class FiltrosAplicados(BaseModel):
    ano_inicio: int
    ano_fim: int
    classes: list[str]
    incluir_imputados: bool


class IndicadorUF(BaseModel):
    sigla_uf: str
    nome_uf: str
    regiao: str
    populacao: int = Field(description="População residente, Censo 2022.")
    potencia_mw: float
    qtd_empreendimentos: int
    qtd_imputados: int = Field(
        description="Registros sem fonte informada contados como solares."
    )
    watts_por_habitante: float
    empreendimentos_por_100k_hab: float


class RespostaIndicadores(BaseModel):
    filtros: FiltrosAplicados
    media_brasil: dict[str, float]
    itens: list[IndicadorUF]


class ItemRanking(IndicadorUF):
    posicao: int = Field(description="1 = maior valor na métrica.")
    valor: float = Field(description="Valor da métrica usada no ranking.")


class RespostaRanking(BaseModel):
    metrica: NomeMetrica
    rotulo: str
    unidade: str
    ordem: Literal["desc", "asc"]
    filtros: FiltrosAplicados
    media_brasil: float | None = Field(
        description="Referência nacional (só métricas per capita)."
    )
    itens: list[ItemRanking]


class CrescimentoUF(BaseModel):
    ano_base: int
    ano_final: int
    acumulado_base_mw: float
    acumulado_final_mw: float
    cagr_pct: float | None = Field(
        description="Crescimento médio anual do parque instalado (%)."
    )
    cagr_brasil_pct: float


class AdesaoICMS(BaseModel):
    sigla_uf: str
    nome_uf: str
    convenio_adesao: str = Field(examples=["157/15"])
    data_adesao: date
    inicio_efeitos: date = Field(
        description="Data a partir da qual a isenção produz efeitos."
    )
    ano_inicio_efeitos: int
    meses_desde_inicio: int
    forma_inclusao: str
    observacao: str | None = None
    origem_texto: str = Field(description="confaz_online ou referencia_local.")


class DetalheUF(BaseModel):
    filtros: FiltrosAplicados
    indicadores: IndicadorUF
    posicoes: dict[str, int] = Field(description="Posição (1 = maior) em cada métrica.")
    media_brasil: dict[str, float]
    crescimento: CrescimentoUF
    quadrante: str
    icms: AdesaoICMS | None
    noticias_relacionadas: int = Field(
        description="Notícias do corpus que mencionam a UF."
    )


class PontoSerie(BaseModel):
    ano: int
    potencia_mw: float = Field(description="Potência conectada no ano.")
    qtd_empreendimentos: int
    potencia_acumulada_mw: float
    qtd_acumulada: int
    crescimento_pct: float | None = Field(
        description="Crescimento do parque sobre o ano anterior (%)."
    )
    ano_parcial: bool


class SerieUF(BaseModel):
    sigla_uf: str
    nome_uf: str
    filtros: FiltrosAplicados
    pontos: list[PontoSerie]


class ItemOportunidade(BaseModel):
    sigla_uf: str
    nome_uf: str
    regiao: str
    watts_por_habitante: float
    potencia_mw: float
    cagr_pct: float | None
    quadrante: str


class RespostaOportunidades(BaseModel):
    ano_base: int
    ano_final: int
    referencia: dict[str, float] = Field(
        description="Referências nacionais usadas nos cortes."
    )
    quadrantes: dict[str, str] = Field(description="Descrição de cada quadrante.")
    itens: list[ItemOportunidade]


# ═══════════════════ Notícias ═══════════════════


class Noticia(BaseModel):
    id: str
    fonte: str
    url: str
    data_publicacao: datetime | None
    titulo: str
    linha_fina: str | None = None
    ufs_mencionadas: list[str]
    nivel_texto: str = Field(description="integral ou metadados.")
    tag_origem: str | None = None
    resumo: str | None = Field(default=None, description="Preenchido pelo LLM no TP4.")
    sentimento: str | None = Field(
        default=None, description="Preenchido pelo LLM no TP4."
    )


class NoticiaDetalhe(Noticia):
    texto: str | None = None
    texto_para_modelo: str = Field(
        description="Entrada que o modelo de linguagem receberá no TP4 (respeita o nível de texto)."
    )


class PaginaNoticias(BaseModel):
    total: int = Field(description="Total de notícias que atendem aos filtros.")
    limite: int
    deslocamento: int
    itens: list[Noticia]


class FonteResumo(BaseModel):
    fonte: str
    quantidade: int
    niveis_texto: list[str]
    mais_recente: datetime | None


class NovaNoticia(BaseModel):
    """Notícia enviada por um usuário ou sistema externo."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [
                {
                    "fonte": "Agência Gov",
                    "url": "https://agenciagov.ebc.com.br/noticias/202607/exemplo",
                    "titulo": "Geração distribuída chega a 50 GW no Brasil",
                    "data_publicacao": "2026-07-23",
                    "linha_fina": "Maranhão e Piauí lideram o crescimento no Nordeste",
                    "texto": None,
                }
            ]
        },
    )

    fonte: str = Field(min_length=2, max_length=120)
    url: HttpUrl
    titulo: str = Field(min_length=10, max_length=300)
    data_publicacao: date
    linha_fina: str | None = Field(default=None, max_length=600)
    texto: str | None = Field(
        default=None,
        max_length=50_000,
        description="Só envie o texto integral se a licença da fonte permitir reprodução.",
    )

    @field_validator("data_publicacao")
    @classmethod
    def data_plausivel(cls, valor: date) -> date:
        if valor > date.today():
            raise ValueError("a data de publicação não pode estar no futuro")
        if valor < DATA_MINIMA_NOTICIA:
            raise ValueError(
                f"datas anteriores a {DATA_MINIMA_NOTICIA:%d/%m/%Y} estão fora do escopo"
            )
        return valor


# ═══════════════════ Comparações ═══════════════════


class PedidoComparacao(BaseModel):
    """Indicador próprio por UF, para comparação com a adoção de energia solar."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "nome_indicador": "clientes",
                    "valores": {"RS": 120, "SC": 85, "PR": 60, "SP": 40, "MT": 15},
                    "metrica": "watts_por_habitante",
                }
            ]
        }
    )

    nome_indicador: str = Field(min_length=1, max_length=60, examples=["clientes"])
    valores: dict[str, float] = Field(description="Sigla da UF -> valor.")
    metrica: NomeMetrica = NomeMetrica.watts_por_habitante
    ano_inicio: int | None = None
    ano_fim: int | None = None
    incluir_imputados: bool = True

    @field_validator("valores")
    @classmethod
    def ufs_validas(cls, valores: dict[str, float]) -> dict[str, float]:
        normalizados = {
            sigla.strip().upper(): valor for sigla, valor in valores.items()
        }
        invalidas = sorted(set(normalizados) - set(esquema.UFS))
        if invalidas:
            raise ValueError(f"siglas de UF inválidas: {invalidas}")
        if len(normalizados) < 3:
            raise ValueError("informe valores para ao menos 3 UFs")
        return normalizados


class ItemComparacao(BaseModel):
    sigla_uf: str
    nome_uf: str
    valor_usuario: float
    valor_metrica: float
    posicao_usuario: int
    posicao_metrica: int
    diferenca_posicoes: int = Field(
        description="posicao_usuario - posicao_metrica. Positivo: presença do usuário abaixo da adoção."
    )


class RespostaComparacao(BaseModel):
    nome_indicador: str
    metrica: NomeMetrica
    filtros: FiltrosAplicados
    n_ufs: int
    correlacao_spearman: float | None
    interpretacao: str
    itens: list[ItemComparacao]
