"""Modelos de linguagem locais (TP4): métricas, catálogo, gerenciador e inferência.

Os testes do gerenciador usam uma fábrica falsa (sem PyTorch, sem download).
Os de inferência criam modelos MINÚSCULOS na hora — mesma arquitetura dos
modelos reais (T5 e DeBERTa-v2), pesos aleatórios e tokenizador treinado no
próprio corpus — para exercitar o código de verdade sem baixar nada. A saída
desses modelos não tem sentido; o que se verifica é o contrato.
"""

import shutil
import threading
from typing import ClassVar

import pandas as pd
import pytest

from src.ia import benchmark, catalogo, metricas
from src.ia.catalogo import Arquitetura, ModeloConfig, Tarefa
from src.ia.modelos_hf import (
    ResultadoClassificacao,
    ResultadoRelevancia,
    ResultadoResumo,
)
from src.ia.motor import EstadoModelo, GerenciadorModelos, ModeloIndisponivel
from src.servicos import dados
from src.servicos.texto import texto_para_modelo

# ═══════════════════ Métricas ═══════════════════


def test_rouge_extremos_e_acentos():
    assert metricas.rouge_1("geração solar cresce", "geração solar cresce") == 1.0
    assert metricas.rouge_1("abc", "xyz") == 0.0
    assert metricas.rouge_1("", "algo") == 0.0
    # Acento não pode partir a palavra (falha do pacote rouge-score)
    assert metricas.tokenizar("Geração elétrica") == ["geração", "elétrica"]


def test_rouge_l_premia_a_ordem():
    referencia = "aneel aprova nova regra para geração distribuída"
    mesma_ordem = "aneel aprova regra geração"
    invertida = "geração regra aprova aneel"
    assert metricas.rouge_1(mesma_ordem, referencia) == metricas.rouge_1(
        invertida, referencia
    )
    assert metricas.rouge_l(mesma_ordem, referencia) > metricas.rouge_l(
        invertida, referencia
    )


def test_acuracia_e_f1_macro():
    verdade = ["a", "a", "a", "b"]
    previsto = ["a", "a", "a", "a"]
    assert metricas.acuracia(verdade, previsto) == 0.75
    # F1 macro expõe a classe "b" ignorada, que a acurácia esconde
    assert metricas.f1_macro(verdade, previsto, ["a", "b"]) == pytest.approx(
        0.4286, abs=1e-3
    )


# ═══════════════════ Catálogo ═══════════════════


def test_padroes_existem_e_executam_a_tarefa():
    for tarefa in Tarefa:
        assert tarefa in catalogo.modelo_da_tarefa(tarefa).tarefas


def test_variavel_de_ambiente_troca_e_valida(monkeypatch):
    monkeypatch.setenv("SOLARGAP_MODELO_CLASSIFICACAO", "minilm-nli")
    assert catalogo.modelo_da_tarefa(Tarefa.tom).chave == "minilm-nli"
    monkeypatch.setenv("SOLARGAP_MODELO_RESUMO", "mdeberta-nli")  # não resume
    with pytest.raises(ValueError, match="não executa"):
        catalogo.modelo_da_tarefa(Tarefa.resumo)
    monkeypatch.setenv("SOLARGAP_MODELO_RESUMO", "inexistente")
    with pytest.raises(ValueError, match="não existe"):
        catalogo.modelo_da_tarefa(Tarefa.resumo)


def test_generativo_so_entra_quando_pedido():
    sem = {c.chave for c in catalogo.candidatos_da_tarefa(Tarefa.resumo)}
    com = {
        c.chave
        for c in catalogo.candidatos_da_tarefa(Tarefa.resumo, incluir_generativo=True)
    }
    assert "qwen2.5-1.5b" in com - sem


# ═══════════════════ Entrada do modelo ═══════════════════


def test_linha_fina_igual_ao_lide_nao_se_repete():
    lide = "A Aneel aprovou hoje novas regras para a geração distribuída no país."
    texto = lide + " O texto continua com detalhes da decisão."
    entrada = texto_para_modelo("Título", lide, texto, "integral")
    assert entrada.count("A Aneel aprovou") == 1
    propria = texto_para_modelo(
        "Título", "Resumo escrito pela redação.", texto, "integral"
    )
    assert "Resumo escrito pela redação." in propria


# ═══════════════════ Gerenciador (fábrica falsa) ═══════════════════


class ModeloFalso:
    cargas: ClassVar[list] = []

    def __init__(self, config, dispositivo):
        self.config = config

    def carregar(self):
        ModeloFalso.cargas.append(self.config.chave)
        if self.config.chave == "quebrado":
            raise OSError("arquivo de pesos ausente")

    def resumir(self, texto):
        return ResultadoResumo("resumo falso", len(texto.split()), False)

    def classificar(self, texto, hipoteses):
        return ResultadoClassificacao(
            "neutro", 0.5, dict.fromkeys(hipoteses, 0.33), 10, False
        )

    def avaliar_hipotese(self, texto, hipotese, limiar):
        return ResultadoRelevancia(True, 0.9, 10, False)


def _config(chave, arquitetura, tarefas):
    return ModeloConfig(chave, f"falso/{chave}", arquitetura, tarefas, "MIT", 512)


@pytest.fixture
def configs():
    nli = _config("nli", Arquitetura.nli, catalogo.TAREFAS_CLASSIFICACAO)
    return {
        Tarefa.resumo: _config("t5", Arquitetura.seq2seq, (Tarefa.resumo,)),
        Tarefa.tom: nli,
        Tarefa.relevancia: nli,
    }


def test_estados_e_modelo_compartilhado(configs):
    ModeloFalso.cargas = []
    gerenciador = GerenciadorModelos(configs, dispositivo="cpu", fabrica=ModeloFalso)
    assert gerenciador.estado(Tarefa.resumo) == EstadoModelo.nao_carregado
    with pytest.raises(ModeloIndisponivel) as erro:
        gerenciador.resumir("texto")
    assert erro.value.retry_after is None

    gerenciador.carregar()
    assert gerenciador.todas_prontas()
    assert sorted(ModeloFalso.cargas) == ["nli", "t5"]  # NLI carregado uma vez só
    assert gerenciador.resumir("um dois três").resumo == "resumo falso"
    assert gerenciador.executar(Tarefa.relevancia, "x").relevante is True


def test_falha_na_carga_isola_a_tarefa(configs):
    configs[Tarefa.resumo] = _config("quebrado", Arquitetura.seq2seq, (Tarefa.resumo,))
    gerenciador = GerenciadorModelos(configs, dispositivo="cpu", fabrica=ModeloFalso)
    gerenciador.carregar()
    situacao = gerenciador.situacao(Tarefa.resumo)
    assert situacao.estado == EstadoModelo.falhou and "pesos ausente" in situacao.erro
    with pytest.raises(ModeloIndisponivel, match="falhou"):
        gerenciador.resumir("texto")
    assert gerenciador.classificar_tom("texto").rotulo == "neutro"  # o resto segue


def test_carga_em_segundo_plano_responde_carregando(configs):
    liberar = threading.Event()

    class Lento(ModeloFalso):
        def carregar(self):
            liberar.wait(5)

    gerenciador = GerenciadorModelos(configs, dispositivo="cpu", fabrica=Lento)
    gerenciador.carregar(em_segundo_plano=True)
    with pytest.raises(ModeloIndisponivel) as erro:
        gerenciador.resumir("texto")
    assert erro.value.estado == EstadoModelo.carregando and erro.value.retry_after
    liberar.set()
    gerenciador.aguardar_carga(5)
    assert gerenciador.todas_prontas()


# ═══════════════════ Benchmark: amostras e rótulos ═══════════════════


def test_amostra_de_resumo_nao_vaza_a_referencia():
    amostra = benchmark.amostra_resumo(dados.carregar_corpus())
    assert len(amostra) > 30
    for entrada, referencia in zip(amostra["entrada"], amostra["referencia"]):
        assert referencia[:60] not in entrada


def test_rotulos_normalizam_e_rejeitam_invalidos(tmp_path):
    caminho = tmp_path / "rotulos.csv"
    pd.DataFrame(
        {"id": ["a", "b"], "relevante": ["Sim", "não"], "tom": ["Favorável", ""]}
    ).to_csv(caminho, sep=";", index=False, encoding="utf-8-sig")
    rotulos = benchmark.carregar_rotulos(caminho)
    assert rotulos["relevante"].tolist() == ["sim", "nao"]
    assert rotulos["tom"].tolist() == ["favoravel", ""]

    # Excel com Windows em inglês grava com vírgula: também precisa funcionar
    pd.DataFrame({"id": ["c"], "relevante": ["talvez"], "tom": ["neutro"]}).to_csv(
        caminho, sep=",", index=False
    )
    with pytest.raises(ValueError, match="fora do padrão"):
        benchmark.carregar_rotulos(caminho)


# ═══════════════════ Inferência real com modelos minúsculos ═══════════════════


@pytest.fixture(scope="module")
def modelos_minusculos(tmp_path_factory):
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    spm = pytest.importorskip("sentencepiece")
    from transformers import (
        DebertaV2Config,
        DebertaV2ForSequenceClassification,
        DebertaV2Tokenizer,
        T5Config,
        T5ForConditionalGeneration,
        T5Tokenizer,
    )

    pasta = tmp_path_factory.mktemp("modelos")
    textos = pasta / "corpus.txt"
    textos.write_text(
        "\n".join(dados.carregar_corpus()["texto"].dropna()), encoding="utf-8"
    )
    spm.SentencePieceTrainer.train(
        input=str(textos),
        model_prefix=str(pasta / "spm"),
        vocab_size=600,
        pad_id=0,
        eos_id=1,
        unk_id=2,
        bos_id=-1,
        minloglevel=2,
    )

    (pasta / "t5").mkdir()
    shutil.copy(pasta / "spm.model", pasta / "t5" / "spiece.model")
    tok_t5 = T5Tokenizer.from_pretrained(pasta / "t5", extra_ids=0)
    T5ForConditionalGeneration(
        T5Config(
            vocab_size=len(tok_t5),
            d_model=32,
            d_ff=64,
            num_layers=2,
            num_heads=2,
            d_kv=16,
            decoder_start_token_id=0,
            pad_token_id=0,
            eos_token_id=1,
        )
    ).save_pretrained(pasta / "t5")
    tok_t5.save_pretrained(pasta / "t5")

    (pasta / "nli").mkdir()
    shutil.copy(pasta / "spm.model", pasta / "nli" / "spm.model")
    tok_nli = DebertaV2Tokenizer.from_pretrained(pasta / "nli")
    rotulos = {"entailment": 0, "neutral": 1, "contradiction": 2}
    DebertaV2ForSequenceClassification(
        DebertaV2Config(
            vocab_size=len(tok_nli) + 8,
            hidden_size=32,
            num_hidden_layers=2,
            num_attention_heads=2,
            intermediate_size=64,
            max_position_embeddings=128,
            num_labels=3,
            label2id=rotulos,
            id2label={v: k for k, v in rotulos.items()},
        )
    ).save_pretrained(pasta / "nli")
    tok_nli.save_pretrained(pasta / "nli")

    t5 = ModeloConfig(
        "t5-minusculo",
        str(pasta / "t5"),
        Arquitetura.seq2seq,
        (Tarefa.resumo,),
        "teste",
        64,
        max_tokens_saida=8,
    )
    nli = ModeloConfig(
        "nli-minusculo",
        str(pasta / "nli"),
        Arquitetura.nli,
        catalogo.TAREFAS_CLASSIFICACAO,
        "teste",
        64,
    )
    return {Tarefa.resumo: t5, Tarefa.tom: nli, Tarefa.relevancia: nli}


def test_inferencia_real_respeita_o_contrato(modelos_minusculos):
    gerenciador = GerenciadorModelos(modelos_minusculos, dispositivo="cpu")
    gerenciador.carregar()
    assert gerenciador.todas_prontas()
    noticia = dados.carregar_corpus()["texto"].iloc[0]  # bem maior que 64 tokens

    resumo = gerenciador.resumir(noticia)
    assert (
        isinstance(resumo.resumo, str)
        and resumo.truncado
        and resumo.tokens_entrada > 64
    )

    tom = gerenciador.classificar_tom(noticia)
    assert set(tom.distribuicao) == set(catalogo.ROTULOS_TOM)
    assert sum(tom.distribuicao.values()) == pytest.approx(1, abs=1e-3)
    assert tom.rotulo in catalogo.ROTULOS_TOM and tom.truncado

    relevancia = gerenciador.avaliar_relevancia("Energia solar.")
    assert 0 <= relevancia.probabilidade <= 1 and not relevancia.truncado
    assert relevancia.relevante == (
        relevancia.probabilidade >= catalogo.LIMIAR_RELEVANCIA
    )


def test_benchmark_ponta_a_ponta(modelos_minusculos):
    corpus = dados.carregar_corpus()
    amostra = benchmark.amostra_resumo(corpus, limite=3)
    linhas, saidas = benchmark.avaliar_resumo(
        [modelos_minusculos[Tarefa.resumo]], "cpu", amostra
    )
    assert [linha["modelo"] for linha in linhas] == ["baseline_lide", "t5-minusculo"]
    assert linhas[1]["erro"] is None and linhas[1]["tempo_medio_s"] is not None
    assert 0 <= linhas[1]["rouge1"] <= 1 and "t5-minusculo" in saidas

    rotulos = (
        corpus[["id", "titulo"]]
        .head(4)
        .assign(
            relevante=["sim", "sim", "nao", ""], tom=["favoravel", "neutro", "", ""]
        )
    )
    linhas, saidas = benchmark.avaliar_classificacao(
        [modelos_minusculos[Tarefa.tom]], "cpu", rotulos, corpus
    )
    por_tarefa = {linha["tarefa"]: linha for linha in linhas}
    assert por_tarefa["relevancia"]["n_itens"] == 3  # a linha sem rótulo fica de fora
    assert por_tarefa["tom"]["n_itens"] == 2  # tom só nas relevantes
    assert "acuracia" in por_tarefa["tom"]


def test_falha_de_um_candidato_nao_derruba_o_benchmark(modelos_minusculos):
    quebrado = ModeloConfig(
        "inexistente",
        "/caminho/que/nao/existe",
        Arquitetura.seq2seq,
        (Tarefa.resumo,),
        "teste",
        64,
    )
    amostra = benchmark.amostra_resumo(dados.carregar_corpus(), limite=2)
    linhas, _ = benchmark.avaliar_resumo([quebrado], "cpu", amostra)
    assert linhas[1]["erro"] and linhas[1]["modelo"] == "inexistente"
