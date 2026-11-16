"""
PROJETO: SolarGap Brasil
ARQUIVO: catalogo.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 13/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Catálogo dos modelos de linguagem avaliados no TP4 e escolha do modelo
    padrão de cada tarefa. Nada aqui baixa ou carrega modelo: é só configuração.

CRITÉRIOS DO ENUNCIADO (TP4):
    desempenho          medido no benchmark (src/ia/benchmark.py)
    custo computacional parâmetros, tempo por notícia e memória (GPU e CPU)
    acessibilidade      todos são baixados do HuggingFace Hub e rodam localmente

POR QUE MODELOS DE TAREFA E NÃO UM CHATBOT:
    Um LLM generativo pequeno inventa números com facilidade, o que é grave num
    projeto cujo valor é o dado validado. Para resumir e classificar notícias,
    modelos especializados são menores, mais rápidos e mais previsíveis. O
    generativo entra como candidato opcional no benchmark, para que a escolha
    seja medida e não suposta.

TROCA DE MODELO SEM MEXER NO CÓDIGO:
    SOLARGAP_MODELO_RESUMO=ptt5-summ-xlsum
    SOLARGAP_MODELO_CLASSIFICACAO=minilm-nli
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class Tarefa(str, Enum):
    resumo = "resumo"
    tom = "tom"
    relevancia = "relevancia"


class Arquitetura(str, Enum):
    seq2seq = "seq2seq"  # codificador-decodificador (T5): texto -> texto
    nli = "nli"  # inferência textual, usada como classificador zero-shot
    generativo = "generativo"  # LLM de instrução (só decodificador)


@dataclass(frozen=True)
class ModeloConfig:
    chave: str
    hf_id: str  # id no HuggingFace Hub ou caminho de uma pasta local
    arquitetura: Arquitetura
    tarefas: tuple[Tarefa, ...]
    licenca: str
    max_tokens_entrada: int
    tokenizer_id: str | None = None  # quando o tokenizador mora em outro repositório
    max_tokens_saida: int = 160
    descricao: str = ""
    observacao: str = ""

    @property
    def id_tokenizer(self) -> str:
        return self.tokenizer_id or self.hf_id


TAREFAS_CLASSIFICACAO = (Tarefa.tom, Tarefa.relevancia)

CANDIDATOS: dict[str, ModeloConfig] = {
    "ptt5-summ": ModeloConfig(
        chave="ptt5-summ",
        hf_id="recogna-nlp/ptt5-base-summ",
        tokenizer_id="unicamp-dl/ptt5-base-portuguese-vocab",
        arquitetura=Arquitetura.seq2seq,
        tarefas=(Tarefa.resumo,),
        licenca="MIT",
        max_tokens_entrada=512,
        descricao="PTT5 base ajustado no RecognaSumm, corpus de notícias brasileiras.",
    ),
    "ptt5-summ-xlsum": ModeloConfig(
        chave="ptt5-summ-xlsum",
        hf_id="recogna-nlp/ptt5-base-summ-xlsum",
        tokenizer_id="unicamp-dl/ptt5-base-portuguese-vocab",
        arquitetura=Arquitetura.seq2seq,
        tarefas=(Tarefa.resumo,),
        licenca="CC BY-NC-SA 4.0",
        max_tokens_entrada=512,
        descricao="PTT5 base ajustado no XL-Sum (notícias da BBC em português).",
        observacao="Licença não comercial: aceitável em projeto acadêmico.",
    ),
    "qwen2.5-1.5b": ModeloConfig(
        chave="qwen2.5-1.5b",
        hf_id="Qwen/Qwen2.5-1.5B-Instruct",
        arquitetura=Arquitetura.generativo,
        tarefas=(Tarefa.resumo,),
        licenca="Apache-2.0",
        max_tokens_entrada=2048,
        descricao="LLM de instrução multilíngue, candidato generativo de comparação.",
        observacao="Opcional no benchmark (download de ~3 GB); fp16 na GPU.",
    ),
    "mdeberta-nli": ModeloConfig(
        chave="mdeberta-nli",
        hf_id="MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
        arquitetura=Arquitetura.nli,
        tarefas=TAREFAS_CLASSIFICACAO,
        licenca="MIT",
        max_tokens_entrada=512,
        descricao="mDeBERTa-v3 base ajustado em NLI em 27 idiomas, inclusive português.",
        observacao="Não suporta fp16; roda sempre em fp32.",
    ),
    "minilm-nli": ModeloConfig(
        chave="minilm-nli",
        hf_id="MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli",
        arquitetura=Arquitetura.nli,
        tarefas=TAREFAS_CLASSIFICACAO,
        licenca="conferir no cartão do modelo",
        max_tokens_entrada=512,
        descricao="MiniLMv2 de 6 camadas: versão menor e mais rápida, menos precisa.",
    ),
}

PADRAO = {
    Tarefa.resumo: "ptt5-summ",
    Tarefa.tom: "mdeberta-nli",
    Tarefa.relevancia: "mdeberta-nli",
}

VARIAVEL_AMBIENTE = {
    Tarefa.resumo: "SOLARGAP_MODELO_RESUMO",
    Tarefa.tom: "SOLARGAP_MODELO_CLASSIFICACAO",
    Tarefa.relevancia: "SOLARGAP_MODELO_CLASSIFICACAO",
}


def modelo_da_tarefa(tarefa: Tarefa) -> ModeloConfig:
    """Modelo em uso para a tarefa: variável de ambiente, ou o padrão do catálogo."""
    chave = os.getenv(VARIAVEL_AMBIENTE[tarefa]) or PADRAO[tarefa]
    if chave not in CANDIDATOS:
        raise ValueError(
            f"Modelo '{chave}' ({VARIAVEL_AMBIENTE[tarefa]}) não existe no catálogo. "
            f"Opções: {sorted(CANDIDATOS)}"
        )
    config = CANDIDATOS[chave]
    if tarefa not in config.tarefas:
        raise ValueError(f"O modelo '{chave}' não executa a tarefa '{tarefa.value}'.")
    return config


def candidatos_da_tarefa(
    tarefa: Tarefa, incluir_generativo: bool = False
) -> list[ModeloConfig]:
    return [
        c
        for c in CANDIDATOS.values()
        if tarefa in c.tarefas
        and (incluir_generativo or c.arquitetura != Arquitetura.generativo)
    ]


# ═══════════════════ Hipóteses da classificação zero-shot ═══════════════════
#
# Um modelo de NLI recebe um par (premissa, hipótese) e diz se a premissa
# implica a hipótese. Para classificar, a notícia é a premissa e cada rótulo
# vira uma frase-hipótese. Frases descritivas funcionam melhor que palavras
# soltas ("positivo"), porque o modelo foi treinado com frases.
#
# "Tom" e não "sentimento": notícia de política energética não expressa emoção;
# o que interessa é se ela relata avanço ou obstáculo para a energia solar.
# A coluna do corpus continua se chamando "sentimento" (contrato do TP3).

HIPOTESE_RELEVANCIA = "Esta notícia trata de energia solar."
LIMIAR_RELEVANCIA = 0.5

HIPOTESES_TOM = {
    "favoravel": "Esta notícia relata avanços, benefícios ou incentivos para a energia solar.",
    "desfavoravel": "Esta notícia relata problemas, custos, riscos ou retrocessos para a energia solar.",
    "neutro": "Esta notícia apenas informa, sem apresentar a energia solar como positiva ou negativa.",
}
ROTULOS_TOM = tuple(HIPOTESES_TOM)

# ═══════════════════ Tarefas experimentais ═══════════════════
#
# Resultado do benchmark (docs/escolha_modelo.md): o tom zero-shot acertou 43%
# das 23 notícias relevantes, abaixo dos 83% de prever sempre "favoravel". Ele
# continua disponível na API para demonstração, sempre marcado como
# experimental, mas não é gravado no corpus nem exibido como indicador.

TAREFAS_EXPERIMENTAIS = frozenset({Tarefa.tom})
AVISO_TOM = (
    "Tarefa experimental: no benchmark do projeto, o tom acertou 43% das notícias "
    "rotuladas, abaixo da linha de base de 83% (responder sempre 'favoravel'). "
    "Não use o resultado como indicador."
)
