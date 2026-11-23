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
    resumo: str | None = Field(
        default=None,
        description=(
            "Resumo gerado pelo modelo local (PTT5). Sempre nulo para fontes cuja licença "
            "proíbe obra derivada (CC BY-ND: ANEEL, MME, Agência Gov); leia a matéria pela url."
        ),
    )
    sentimento: str | None = Field(
        default=None,
        description="Reservado. O tom não é gravado: ficou abaixo da linha de base no benchmark.",
    )
    relevante: bool | None = Field(
        default=None,
        description="Se o modelo julgou que a notícia trata de energia solar (null = não avaliada).",
    )
    relevancia_prob: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Probabilidade de tratar de energia solar.",
    )
    relevancia_por_termo: bool | None = Field(
        default=None,
        description=(
            "Relevante pela regra de palavra: o título cita um termo de geração distribuída "
            "(Lei 14.300, micro/minigeração...), mesmo com probabilidade abaixo do limiar."
        ),
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


# ═══════════════════ IA — modelos de linguagem locais (TP4) ═══════════════════


class TarefaIA(StrEnum):
    resumo = "resumo"
    relevancia = "relevancia"
    tom = "tom"


class PedidoProcessamento(BaseModel):
    """Texto livre a ser processado pelos modelos locais."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [
                {
                    "texto": (
                        "A potência instalada de micro e minigeração distribuída solar no "
                        "Brasil ultrapassou 40 GW, segundo a ANEEL. Minas Gerais, São Paulo "
                        "e Rio Grande do Sul lideram o número de sistemas conectados."
                    ),
                    "tarefas": ["resumo", "relevancia"],
                }
            ]
        },
    )

    texto: str = Field(
        min_length=40,
        max_length=20_000,
        description="Texto em português. Acima de ~350 palavras, o modelo lê só o início (truncado=true).",
    )
    tarefas: list[TarefaIA] = Field(
        default=[TarefaIA.resumo, TarefaIA.relevancia],
        min_length=1,
        description="Tarefas a executar. 'tom' é experimental.",
    )

    @field_validator("tarefas")
    @classmethod
    def sem_repeticao(cls, valor: list[TarefaIA]) -> list[TarefaIA]:
        return list(dict.fromkeys(valor))

    @field_validator("texto")
    @classmethod
    def texto_com_palavras(cls, valor: str) -> str:
        if len(valor.split()) < 8:
            raise ValueError("envie um texto com pelo menos 8 palavras")
        return valor


class ResultadoResumoIA(BaseModel):
    resumo: str
    tokens_entrada: int = Field(description="Tamanho do texto em tokens do modelo.")
    truncado: bool = Field(
        description="Se o texto passou do limite e só o início foi lido."
    )


class ResultadoRelevanciaIA(BaseModel):
    relevante: bool
    probabilidade: float = Field(ge=0, le=1)
    limiar: float = Field(description="Probabilidade mínima para considerar relevante.")
    tokens_entrada: int
    truncado: bool
    por_termo_gd: bool = Field(
        default=False,
        description=(
            "Relevante pela regra de palavra: o título (ou a primeira linha do texto) cita "
            "um termo de geração distribuída, mesmo com probabilidade abaixo do limiar."
        ),
    )


class ResultadoTomIA(BaseModel):
    rotulo: Literal["favoravel", "desfavoravel", "neutro"]
    confianca: float = Field(ge=0, le=1)
    distribuicao: dict[str, float]
    tokens_entrada: int
    truncado: bool
    experimental: bool = True
    aviso: str


class ResultadosIA(BaseModel):
    resumo: ResultadoResumoIA | None = None
    relevancia: ResultadoRelevanciaIA | None = None
    tom: ResultadoTomIA | None = None


class ModeloUsado(BaseModel):
    tarefa: TarefaIA
    modelo: str = Field(description="Identificador no HuggingFace Hub.")
    licenca: str


class RespostaProcessamento(BaseModel):
    origem: str = Field(
        description="'texto' (enviado na requisição) ou 'noticia:<id>'."
    )
    tarefas: list[TarefaIA]
    caracteres_entrada: int
    resultados: ResultadosIA
    modelos: list[ModeloUsado]
    dispositivo: str = Field(description="cuda (GPU) ou cpu.")
    duracao_ms: int = Field(description="Tempo total de inferência.")


class EstadoTarefaIA(BaseModel):
    tarefa: TarefaIA
    modelo: str
    estado: Literal["nao_carregado", "carregando", "pronto", "falhou"]
    experimental: bool
    segundos_carga: float | None = None
    carregado_em: datetime | None = None
    erro: str | None = None


class StatusIA(BaseModel):
    pronto: bool = Field(description="Se todas as tarefas podem ser executadas.")
    dispositivo: str | None = Field(description="Definido quando a carga começa.")
    timeout_inferencia_s: float
    tarefas: list[EstadoTarefaIA]


# ═══════════════════ Potencial solar (TP4.5, Tarefa 7) ═══════════════════


class NomeVisao(StrEnum):
    """Visão da base ANEEL 10/2026. Valor fora da lista: HTTP 422."""

    corrigida = "corrigida"
    aneel = "aneel"
    conservadora = "conservadora"


class ResumoPotencial(BaseModel):
    nivel: Literal["brasil", "uf", "municipio"]
    nome: str
    visao: NomeVisao
    n_municipios: int
    domicilios: int = Field(description="Domicílios particulares permanentes ocupados.")
    irradiacao_kwh_m2_dia: float = Field(
        description="Irradiação média (NASA POWER 2023–2025), ponderada pelo kWp potencial."
    )
    x_mwh_ano: float = Field(description="Potencial técnico residencial (x), MWh/ano.")
    y_mwh_ano: float = Field(
        description="Produção estimada (y) da MMGD residencial e rural na própria UC."
    )
    gap_mwh_ano: float = Field(description="x − y. Negativo quando y > x.")
    taxa_realizacao: float = Field(description="y / x (fração; 0,10 = 10%).")
    n_municipios_taxa_acima_1: int = Field(
        description="Municípios com y > x (telhado médio maior que o premissado)."
    )


class PotencialUF(ResumoPotencial):
    uf: str
    regiao: str
    principais_fatores: list[str] = Field(
        description=(
            "Três grupos de fatores de maior contribuição SHAP absoluta na UF, com o "
            "sinal: '+' eleva a taxa (reduz o gap), '−' reduz a taxa (aumenta o gap)."
        )
    )


class Premissas(BaseModel):
    performance_ratio: float
    eficiencia_painel: float
    area_util_telhado_m2: float
    areas_sensibilidade_m2: list[float]
    base_aneel: str


class RespostaPotencialUF(BaseModel):
    visao: NomeVisao
    premissas: Premissas
    brasil: ResumoPotencial
    itens: list[PotencialUF]


class PotencialMunicipio(ResumoPotencial):
    cod_ibge: str
    uf: str
    taxas_por_visao: dict[str, float] = Field(
        description="Taxa de realização nas três visões, para comparação."
    )


class ContribuicaoFator(BaseModel):
    fator: str = Field(description="Nome técnico do fator no modelo.")
    grupo: str = Field(description="Família do fator (chave de ExplicacaoPotencial.grupos).")
    rotulo: str
    rotulo_no_grupo: str = Field(description="Rótulo com o grupo, ex.: 'Renda · média'.")
    valor: float | None = Field(
        description="Valor do fator. Na UF e no Brasil, média ponderada por domicílios."
    )
    valor_texto: str
    contribuicao: float = Field(description="Contribuição SHAP, em fração da taxa.")
    contribuicao_pp: float = Field(description="Contribuição em pontos percentuais.")
    efeito: Literal["eleva", "reduz"]
    frase: str


class GrupoFatores(BaseModel):
    grupo: str
    rotulo: str
    fatores: list[str] = Field(description="Fatores somados neste grupo.")
    contribuicao: float = Field(
        description="Soma das contribuições SHAP dos fatores (o SHAP é aditivo)."
    )
    contribuicao_pp: float
    efeito: Literal["eleva", "reduz"] = Field(
        description="eleva: puxa a taxa para cima (reduz o gap); reduz: o contrário."
    )


class ExplicacaoPotencial(BaseModel):
    nivel: Literal["brasil", "uf", "municipio"]
    nome: str
    cod_ibge: str | None
    visao: NomeVisao
    visao_modelo: NomeVisao = Field(
        description="Visão do alvo em que o modelo SHAP foi treinado."
    )
    taxa_observada: float = Field(description="Taxa de realização na visão pedida.")
    taxa_prevista: float = Field(description="Previsão do modelo (visão corrigida).")
    valor_base: float = Field(description="Média das previsões (referência do SHAP).")
    usado_no_treino: bool = Field(
        description="False para os municípios com y > x, fora do treino."
    )
    diferenca_pp: float = Field(
        description="Taxa observada − prevista, em p.p. Negativa: abaixo do esperado."
    )
    comparacao_esperado: str = Field(
        description="Observada x esperada pelo perfil, em linguagem simples."
    )
    leitura: str = Field(
        description="Resumo em linguagem simples: comparação e grupos separados por sinal."
    )
    aviso_visao: str | None
    puxam_para_baixo: list[str] = Field(
        description="Grupos que mais reduzem a taxa (aumentam o gap), até 3, com ≥ 1 p.p."
    )
    puxam_para_cima: list[str] = Field(
        description="Grupos que mais elevam a taxa (reduzem o gap), até 3, com ≥ 1 p.p."
    )
    grupos: list[GrupoFatores] = Field(
        description="Fatores da mesma família somados, do maior para o menor efeito absoluto."
    )
    fatores: list[ContribuicaoFator] = Field(
        description=(
            "Valores individuais, do maior para o menor efeito absoluto. "
            "Associação, não causalidade."
        )
    )
    ranking_global_visao: list[str] = Field(
        description="Fatores mais importantes no modelo ajustado à visão pedida."
    )


class CenarioPotencial(BaseModel):
    cenario: Literal["ssp245", "ssp585"]
    rotulo_cenario: str
    janela: Literal["2030-2039", "2040-2050"]
    delta_mediano: float = Field(description="Variação relativa da irradiação (mediana).")
    delta_min: float
    delta_max: float
    irradiacao_observada: float
    irradiacao_projetada: float
    irradiacao_projetada_min: float
    irradiacao_projetada_max: float
    x_atual_mwh_ano: float
    x_projetado_mwh_ano: float
    x_projetado_min_mwh_ano: float
    x_projetado_max_mwh_ano: float
    y_atual_mwh_ano: float
    y_projetado_mwh_ano: float
    y_projetado_min_mwh_ano: float
    y_projetado_max_mwh_ano: float
    gap_atual_mwh_ano: float
    gap_projetado_mwh_ano: float
    gap_projetado_min_mwh_ano: float
    gap_projetado_max_mwh_ano: float
    taxa_realizacao: float
    taxa_projetada: float = Field(
        description="Igual à atual no município: a irradiação se cancela em y / x."
    )
    n_modelos: int


class CenariosMunicipio(BaseModel):
    cod_ibge: str
    nome: str
    uf: str
    visao: NomeVisao
    distancia_celula_km: float = Field(
        description="Distância do município à célula de 0,25° com dado usada."
    )
    aviso: str
    itens: list[CenarioPotencial]


# ═══════════════════ Agente (TP5) ═══════════════════


class TrocaHistorico(BaseModel):
    pergunta: str = Field(max_length=1000)
    resposta: str = Field(default="", max_length=8000)


class PedidoAgente(BaseModel):
    pergunta: str = Field(
        min_length=3,
        max_length=1000,
        description="Pergunta em português sobre potencial, gap, fatores ou cenários.",
        examples=["Por que Caxias do Sul está abaixo do esperado e o que fazer?"],
    )
    historico: list[TrocaHistorico] = Field(
        default_factory=list,
        max_length=20,
        description="Trocas anteriores da conversa (memória). O painel envia as últimas.",
    )
    contexto: dict = Field(
        default_factory=dict,
        description="O campo 'contexto' da resposta anterior (recorte da conversa).",
    )
    visao: NomeVisao = NomeVisao.corrigida
    usar_llm: bool = Field(
        default=True,
        description="False força o modo por regras (sem modelo de linguagem).",
    )

    @field_validator("pergunta")
    @classmethod
    def sem_espacos_vazios(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("A pergunta não pode ser vazia.")
        return valor.strip()


class RecorteAgente(BaseModel):
    nivel: Literal["brasil", "uf", "municipio"]
    uf: str | None
    cod_ibge: str | None
    municipio: str | None
    descricao: str
    ufs_citadas: list[str]
    homonimos: list[str]


class FerramentaUsada(BaseModel):
    nome: str
    argumentos: dict
    fatos: list[str]
    dados: dict | list
    erro: str | None


class AcaoRecomendada(BaseModel):
    fator: str
    nivel: str | None = Field(description="alto/baixo em relação à mediana dos municípios.")
    acao: str
    recorte: str | None = Field(default=None, description="Lugar a que a ação se refere.")


class VerificacaoNumeros(BaseModel):
    numeros: int
    verificados: int
    nao_encontrados: list[str]
    taxa: float = Field(description="Fração dos números da resposta presentes nos fatos.")


class RespostaAgenteAPI(BaseModel):
    pergunta: str
    resposta: str = Field(description="Diagnóstico e recomendações em markdown.")
    modo: Literal["llm", "regras", "misto"]
    modelo: str | None
    intencoes: list[str]
    recorte: RecorteAgente
    recorte_herdado: bool = Field(description="True se o recorte veio da conversa anterior.")
    ferramentas: list[FerramentaUsada]
    acoes: list[AcaoRecomendada]
    fatos: list[str]
    verificacao: VerificacaoNumeros
    avisos: list[str]
    tempo_s: float
    visao: NomeVisao
    contexto: dict = Field(description="Envie de volta na próxima pergunta (memória).")


class StatusAgente(BaseModel):
    provedor: str
    modelo: str
    url: str
    llm_disponivel: bool = Field(description="O serviço do modelo respondeu agora.")
    ferramentas: list[str]
