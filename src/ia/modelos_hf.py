"""
PROJETO: SolarGap Brasil
ARQUIVO: modelos_hf.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 13/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Carga e inferência dos modelos com a biblioteca Transformers (HuggingFace).
    É o ÚNICO módulo do projeto que importa torch e transformers, sempre dentro
    das funções — importar este arquivo não exige o PyTorch instalado.

    Resumidor             T5 (seq2seq): gera o resumo com busca em feixe
    ResumidorGenerativo   LLM de instrução: resumo a partir de um prompt
    ClassificadorNLI      classificação zero-shot (tom e relevância)

DOWNLOAD E CACHE:
    Na primeira carga, os pesos são baixados do HuggingFace Hub para o cache
    local (~/.cache/huggingface no Linux/macOS, C:\\Users\\<você>\\.cache\\
    huggingface no Windows). Daí em diante a execução é inteiramente local;
    com HF_HUB_OFFLINE=1 o Transformers nem tenta acessar a rede.

JANELA DE CONTEXTO:
    T5 e DeBERTa leem no máximo 512 tokens (~350 palavras). Notícias maiores
    são truncadas e o resultado informa truncado=True. Em texto jornalístico o
    essencial costuma estar no início (pirâmide invertida), o que torna o corte
    aceitável — mas ele é sempre declarado, nunca silencioso.
"""

from __future__ import annotations

import gc
import logging
import os
from dataclasses import asdict, dataclass

from src.ia.catalogo import Arquitetura, ModeloConfig

logger = logging.getLogger(__name__)


# ═══════════════════ Resultados ═══════════════════


@dataclass
class ResultadoResumo:
    resumo: str
    tokens_entrada: int
    truncado: bool

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResultadoClassificacao:
    rotulo: str
    confianca: float
    distribuicao: dict[str, float]
    tokens_entrada: int
    truncado: bool

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResultadoRelevancia:
    relevante: bool
    probabilidade: float
    tokens_entrada: int
    truncado: bool

    def como_dict(self) -> dict:
        return asdict(self)


# ═══════════════════ Dispositivo ═══════════════════


def escolher_dispositivo(preferencia: str | None = None) -> str:
    """'cuda' se houver GPU NVIDIA utilizável, senão 'cpu'.

    preferencia (ou SOLARGAP_DISPOSITIVO): auto | cuda | cpu. Pedir 'cuda' sem
    GPU disponível é erro explícito — melhor falhar do que rodar 20x mais lento
    sem avisar.
    """
    import torch

    escolha = (preferencia or os.getenv("SOLARGAP_DISPOSITIVO") or "auto").lower()
    if escolha not in {"auto", "cuda", "cpu"}:
        raise ValueError(f"Dispositivo '{escolha}' inválido. Use auto, cuda ou cpu.")
    if escolha == "cpu":
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if escolha == "cuda":
        raise RuntimeError(
            "CUDA solicitada, mas o PyTorch não encontrou GPU. Confira se o torch "
            "instalado é a versão com CUDA (torch.version.cuda não pode ser None)."
        )
    return "cpu"


def descrever_dispositivo(dispositivo: str) -> str:
    import torch

    if dispositivo == "cuda":
        return f"cuda ({torch.cuda.get_device_name(0)})"
    return "cpu"


# ═══════════════════ Base ═══════════════════


class ModeloLocal:
    """Carrega um modelo uma vez e o mantém em memória até liberar()."""

    def __init__(self, config: ModeloConfig, dispositivo: str):
        self.config = config
        self.dispositivo = dispositivo
        self.tokenizer = None
        self.modelo = None

    @property
    def carregado(self) -> bool:
        return self.modelo is not None

    @property
    def parametros(self) -> int:
        return sum(p.numel() for p in self.modelo.parameters()) if self.modelo else 0

    def carregar(self) -> None:
        raise NotImplementedError

    def _finalizar_carga(self, modelo) -> None:
        self.modelo = modelo.to(self.dispositivo).eval()
        logger.info(
            "Modelo %s carregado em %s (%.0f M parâmetros).",
            self.config.chave,
            self.dispositivo,
            self.parametros / 1e6,
        )

    def contar_tokens(self, texto: str) -> int:
        return len(self.tokenizer(texto, add_special_tokens=False)["input_ids"])

    def liberar(self) -> None:
        import torch

        self.modelo = None
        self.tokenizer = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


# ═══════════════════ Resumo ═══════════════════


class Resumidor(ModeloLocal):
    """Sumarização abstrativa com T5 (PTT5)."""

    def carregar(self) -> None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(self.config.id_tokenizer)
        self._finalizar_carga(AutoModelForSeq2SeqLM.from_pretrained(self.config.hf_id))

    def resumir(self, texto: str) -> ResultadoResumo:
        import torch

        limite = self.config.max_tokens_entrada
        tokens = self.contar_tokens(texto)
        entrada = self.tokenizer(
            texto, max_length=limite, truncation=True, return_tensors="pt"
        ).to(self.dispositivo)
        with torch.inference_mode():
            saida = self.modelo.generate(
                **entrada,
                max_new_tokens=self.config.max_tokens_saida,
                min_new_tokens=min(20, self.config.max_tokens_saida // 2),
                num_beams=4,
                no_repeat_ngram_size=3,  # evita frases repetidas, falha comum de T5
                early_stopping=True,
            )
        resumo = self.tokenizer.decode(saida[0], skip_special_tokens=True).strip()
        return ResultadoResumo(
            resumo=resumo, tokens_entrada=tokens, truncado=tokens > limite
        )


class ResumidorGenerativo(ModeloLocal):
    """Resumo com um LLM de instrução — candidato de comparação no benchmark."""

    PROMPT_SISTEMA = (
        "Você resume notícias em português do Brasil com fidelidade ao texto."
    )
    PROMPT_USUARIO = (
        "Resuma a notícia abaixo em no máximo três frases. Use apenas informações "
        "presentes no texto; não acrescente números, nomes ou datas.\n\nNotícia:\n{texto}"
    )

    def carregar(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        precisao = torch.float16 if self.dispositivo == "cuda" else torch.float32
        self.tokenizer = AutoTokenizer.from_pretrained(self.config.id_tokenizer)
        self._finalizar_carga(
            AutoModelForCausalLM.from_pretrained(self.config.hf_id, dtype=precisao)
        )

    def resumir(self, texto: str) -> ResultadoResumo:
        import torch

        limite = self.config.max_tokens_entrada
        tokens = self.contar_tokens(texto)
        if tokens > limite:
            ids = self.tokenizer(texto, add_special_tokens=False)["input_ids"][:limite]
            texto = self.tokenizer.decode(ids)
        mensagens = [
            {"role": "system", "content": self.PROMPT_SISTEMA},
            {"role": "user", "content": self.PROMPT_USUARIO.format(texto=texto)},
        ]
        prompt = self.tokenizer.apply_chat_template(
            mensagens, tokenize=False, add_generation_prompt=True
        )
        entrada = self.tokenizer(prompt, return_tensors="pt").to(self.dispositivo)
        with torch.inference_mode():
            saida = self.modelo.generate(
                **entrada,
                max_new_tokens=self.config.max_tokens_saida,
                do_sample=False,  # determinístico: mesma entrada, mesmo resumo
            )
        novos = saida[0][entrada["input_ids"].shape[1] :]
        resumo = self.tokenizer.decode(novos, skip_special_tokens=True).strip()
        return ResultadoResumo(
            resumo=resumo, tokens_entrada=tokens, truncado=tokens > limite
        )


# ═══════════════════ Classificação zero-shot ═══════════════════


class ClassificadorNLI(ModeloLocal):
    """Classificação zero-shot: cada rótulo vira uma hipótese testada contra a notícia."""

    def carregar(self) -> None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(self.config.id_tokenizer)
        modelo = AutoModelForSequenceClassification.from_pretrained(self.config.hf_id)
        rotulos = {
            nome.lower(): indice for nome, indice in modelo.config.label2id.items()
        }
        try:
            self.idx_implica = next(
                i for n, i in rotulos.items() if n.startswith("entail")
            )
            self.idx_contradiz = next(
                i for n, i in rotulos.items() if n.startswith("contrad")
            )
        except StopIteration as erro:
            raise RuntimeError(
                f"{self.config.hf_id} não parece um modelo de NLI (rótulos: {list(rotulos)})."
            ) from erro
        self._finalizar_carga(modelo)

    def _logits(self, premissa: str, hipoteses: list[str]):
        import torch

        entrada = self.tokenizer(
            [premissa] * len(hipoteses),
            hipoteses,
            truncation="only_first",  # corta a notícia, nunca a hipótese
            max_length=self.config.max_tokens_entrada,
            padding=True,
            return_tensors="pt",
        ).to(self.dispositivo)
        with torch.inference_mode():
            return self.modelo(**entrada).logits.float().cpu()

    def _truncou(self, premissa: str, hipoteses: list[str]) -> tuple[int, bool]:
        tokens = self.contar_tokens(premissa)
        maior_hipotese = max(self.contar_tokens(h) for h in hipoteses)
        especiais = 4  # [CLS] premissa [SEP] hipótese [SEP], com folga
        return (
            tokens,
            tokens + maior_hipotese + especiais > self.config.max_tokens_entrada,
        )

    def classificar(
        self, premissa: str, hipoteses: dict[str, str]
    ) -> ResultadoClassificacao:
        """Rótulo único: softmax dos logits de 'implica' entre as hipóteses."""
        frases = list(hipoteses.values())
        logits = self._logits(premissa, frases)
        probabilidades = logits[:, self.idx_implica].softmax(dim=0).tolist()
        distribuicao = {r: round(p, 4) for r, p in zip(hipoteses, probabilidades)}
        rotulo = max(distribuicao, key=distribuicao.get)
        tokens, truncado = self._truncou(premissa, frases)
        return ResultadoClassificacao(
            rotulo=rotulo,
            confianca=distribuicao[rotulo],
            distribuicao=distribuicao,
            tokens_entrada=tokens,
            truncado=truncado,
        )

    def avaliar_hipotese(
        self, premissa: str, hipotese: str, limiar: float
    ) -> ResultadoRelevancia:
        """Binário: softmax entre 'implica' e 'contradiz' para uma única hipótese."""
        logits = self._logits(premissa, [hipotese])[0]
        par = logits[[self.idx_implica, self.idx_contradiz]].softmax(dim=0)
        probabilidade = round(float(par[0]), 4)
        tokens, truncado = self._truncou(premissa, [hipotese])
        return ResultadoRelevancia(
            relevante=probabilidade >= limiar,
            probabilidade=probabilidade,
            tokens_entrada=tokens,
            truncado=truncado,
        )


CLASSES = {
    Arquitetura.seq2seq: Resumidor,
    Arquitetura.generativo: ResumidorGenerativo,
    Arquitetura.nli: ClassificadorNLI,
}


def criar_modelo(config: ModeloConfig, dispositivo: str) -> ModeloLocal:
    """Fábrica padrão usada pelo gerenciador e pelo benchmark (não carrega ainda)."""
    return CLASSES[config.arquitetura](config, dispositivo)
