"""
PROJETO: SolarGap Brasil
ARQUIVO: benchmark.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 13/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Compara os modelos candidatos do catálogo no corpus do projeto, medindo os
    três critérios do enunciado do TP4: desempenho, custo computacional local
    e acessibilidade. Os resultados justificam a escolha em docs/escolha_modelo.md.

RESUMO — referência sem rotulagem manual:
    Em parte das notícias a linha fina é escrita pela redação e funciona como
    um resumo humano da matéria. Ela vira a referência do ROUGE. Para não haver
    vazamento, o modelo recebe título + texto, SEM a linha fina. Ficam de fora
    as notícias em que a "linha fina" é só o primeiro parágrafo repetido.
    Linha de base: as primeiras palavras do texto ("lide"). Um modelo que não
    supera o lide não justifica seu custo.

CLASSIFICAÇÃO — gabarito manual:
    docs/benchmark/rotulos_benchmark.csv (gerado por src/ia/rotulagem.py e
    preenchido à mão). Relevância é avaliada nas 30 notícias; tom, só nas que
    foram rotuladas como relevantes.

CUSTO MEDIDO POR MODELO:
    tempo de carga, tempo médio e p95 por notícia (após uma execução de
    aquecimento), memória do processo e pico de memória da GPU.

SAÍDAS (docs/benchmark/):
    resultados_<dispositivo>.csv            uma linha por modelo e tarefa
    saidas_resumo_<dispositivo>.csv         resumos lado a lado, para leitura
    saidas_classificacao_<dispositivo>.csv  previsões x rótulos

OBS. DE USO (a partir da raiz):
    python -m src.ia.benchmark                         # GPU se houver
    python -m src.ia.benchmark --dispositivo cpu       # custo sem GPU
    python -m src.ia.benchmark --tarefa resumo --incluir-generativo
    python -m src.ia.benchmark --limite 5              # teste rápido
"""

from __future__ import annotations

import argparse
import logging
import statistics
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.data_acquisition.coletor_base import configurar_logging, obter_project_root
from src.ia import catalogo, metricas
from src.ia.catalogo import ModeloConfig, Tarefa
from src.servicos import dados
from src.servicos.texto import _espacos, texto_para_modelo

PROJECT_ROOT = obter_project_root(__file__)
PASTA_BENCHMARK = PROJECT_ROOT / "docs" / "benchmark"
PASTA_LOGS = PROJECT_ROOT / "logs"
ARQUIVO_ROTULOS = PASTA_BENCHMARK / "rotulos_benchmark.csv"

MIN_PALAVRAS_REFERENCIA = 8

logger = logging.getLogger(__name__)


# ═══════════════════ Amostras ═══════════════════


def amostra_resumo(corpus: pd.DataFrame, limite: int | None = None) -> pd.DataFrame:
    """Notícias cuja linha fina é um resumo próprio, com a entrada sem a linha fina."""
    linha_fina = corpus["linha_fina"].fillna("").astype(str)
    texto = corpus["texto"].fillna("").astype(str)
    titulo = corpus["titulo"].fillna("").astype(str)
    # Fica de fora a linha fina que aparece em qualquer ponto do texto ou do
    # título (algumas matérias da ANEEL repetem o título na descrição): ela
    # seria copiada da entrada e inflaria o ROUGE (vazamento).
    propria = [
        len(lf.split()) >= MIN_PALAVRAS_REFERENCIA
        and _espacos(lf)[:60] not in _espacos(tx)
        and _espacos(lf)[:60] not in _espacos(ti)
        for lf, tx, ti in zip(linha_fina, texto, titulo)
    ]
    amostra = corpus[propria].copy()
    amostra["entrada"] = [
        texto_para_modelo(t, None, x, n)
        for t, x, n in zip(amostra["titulo"], amostra["texto"], amostra["nivel_texto"])
    ]
    amostra["referencia"] = amostra["linha_fina"].str.strip()
    amostra = amostra[["id", "titulo", "texto", "entrada", "referencia"]]
    return amostra.head(limite) if limite else amostra


def baseline_lide(texto: str, palavras: int) -> str:
    return " ".join(str(texto).split()[:palavras])


def _normalizar(valor) -> str:
    valor = (
        unicodedata.normalize("NFKD", str(valor or ""))
        .encode("ascii", "ignore")
        .decode()
    )
    return valor.strip().lower()


def carregar_rotulos(caminho: Path = ARQUIVO_ROTULOS) -> pd.DataFrame:
    """Lê a planilha manual e padroniza: relevante em sim/nao, tom sem acento."""
    # sep=None detecta o separador: o Excel grava ";" ou "," conforme o idioma do Windows.
    rotulos = pd.read_csv(
        caminho, sep=None, engine="python", dtype=str, encoding="utf-8-sig"
    ).fillna("")
    rotulos["relevante"] = (
        rotulos["relevante"].map(_normalizar).replace({"s": "sim", "n": "nao"})
    )
    rotulos["tom"] = rotulos["tom"].map(_normalizar)
    invalidos = rotulos[
        ~rotulos["relevante"].isin(["sim", "nao", ""])
        | ~rotulos["tom"].isin([*catalogo.ROTULOS_TOM, ""])
    ]
    if not invalidos.empty:
        raise ValueError(
            f"Rótulos fora do padrão nas notícias {invalidos['id'].tolist()}. "
            "Use relevante = sim/nao e tom = favoravel/desfavoravel/neutro."
        )
    return rotulos


# ═══════════════════ Medição ═══════════════════


@dataclass
class Medicao:
    config: ModeloConfig
    dispositivo: str
    saidas: list = field(default_factory=list)
    tempos: list[float] = field(default_factory=list)
    carga_s: float | None = None
    parametros_m: float | None = None
    ram_mb: float | None = None
    vram_pico_mb: float | None = None
    erro: str | None = None

    def custo(self) -> dict:
        tempos = sorted(self.tempos)
        p95 = tempos[min(len(tempos) - 1, int(0.95 * len(tempos)))] if tempos else None
        return {
            "modelo": self.config.chave,
            "hf_id": self.config.hf_id,
            "licenca": self.config.licenca,
            "dispositivo": self.dispositivo,
            "parametros_m": self.parametros_m,
            "carga_s": self.carga_s,
            "tempo_medio_s": round(statistics.mean(tempos), 3) if tempos else None,
            "tempo_p95_s": round(p95, 3) if p95 is not None else None,
            "ram_processo_mb": self.ram_mb,
            "vram_pico_mb": self.vram_pico_mb,
            "erro": self.erro,
        }


def _criar_padrao(config: ModeloConfig, dispositivo: str):
    from src.ia.modelos_hf import criar_modelo

    return criar_modelo(config, dispositivo)


def medir(
    config: ModeloConfig,
    dispositivo: str,
    entradas: list[str],
    executar: Callable[[object, str], object],
    fabrica: Callable[[ModeloConfig, str], object] = _criar_padrao,
) -> Medicao:
    """Carrega o modelo, aquece, cronometra cada entrada e libera a memória."""
    import psutil
    import torch

    medicao = Medicao(config, dispositivo)
    modelo = fabrica(config, dispositivo)
    try:
        inicio = time.perf_counter()
        modelo.carregar()
        medicao.carga_s = round(time.perf_counter() - inicio, 1)
        medicao.parametros_m = round(modelo.parametros / 1e6, 1)
        medicao.ram_mb = round(psutil.Process().memory_info().rss / 2**20)
        if dispositivo == "cuda":
            torch.cuda.reset_peak_memory_stats()

        executar(modelo, entradas[0])  # aquecimento: a 1ª chamada inclui alocações
        for i, entrada in enumerate(entradas, start=1):
            inicio = time.perf_counter()
            medicao.saidas.append(executar(modelo, entrada))
            medicao.tempos.append(time.perf_counter() - inicio)
            if i % 10 == 0:
                logger.info("  %s: %d/%d", config.chave, i, len(entradas))

        if dispositivo == "cuda":
            medicao.vram_pico_mb = round(torch.cuda.max_memory_allocated() / 2**20)
    except Exception as erro:  # um candidato que falha não derruba o benchmark
        medicao.erro = f"{type(erro).__name__}: {erro}"[:300]
        logger.exception("Falha em %s", config.chave)
    finally:
        modelo.liberar()
    return medicao


# ═══════════════════ Avaliações ═══════════════════


def avaliar_resumo(
    configs: list[ModeloConfig],
    dispositivo: str,
    amostra: pd.DataFrame,
    fabrica=_criar_padrao,
) -> tuple[list[dict], pd.DataFrame]:
    referencias = amostra["referencia"].tolist()
    palavras_ref = int(statistics.median(len(r.split()) for r in referencias))
    saidas = amostra[["id", "titulo", "referencia"]].copy()
    saidas["lide"] = [baseline_lide(t, palavras_ref) for t in amostra["texto"]]

    def pontuar(textos: list[str]) -> dict:
        return {
            "n_itens": len(textos),
            "rouge1": round(
                statistics.mean(map(metricas.rouge_1, textos, referencias)), 4
            ),
            "rougeL": round(
                statistics.mean(map(metricas.rouge_l, textos, referencias)), 4
            ),
            "palavras_media": round(statistics.mean(len(t.split()) for t in textos), 1),
        }

    linhas = [
        {
            "modelo": "baseline_lide",
            "tarefa": "resumo",
            **pontuar(saidas["lide"].tolist()),
        }
    ]
    for config in configs:
        logger.info("Resumo — %s (%d notícias)", config.chave, len(amostra))
        medicao = medir(
            config,
            dispositivo,
            amostra["entrada"].tolist(),
            lambda m, t: m.resumir(t),
            fabrica,
        )
        linha = {"tarefa": "resumo", **medicao.custo()}
        if not medicao.erro:
            textos = [r.resumo for r in medicao.saidas]
            saidas[config.chave] = textos
            linha |= pontuar(textos)
            linha["truncados_pct"] = round(
                100 * statistics.mean(r.truncado for r in medicao.saidas), 1
            )
        linhas.append(linha)
    return linhas, saidas


def avaliar_classificacao(
    configs: list[ModeloConfig],
    dispositivo: str,
    rotulos: pd.DataFrame,
    corpus: pd.DataFrame,
    fabrica=_criar_padrao,
) -> tuple[list[dict], pd.DataFrame]:
    base = rotulos[["id", "titulo", "relevante", "tom"]].merge(
        corpus[["id", "linha_fina", "texto", "nivel_texto"]], on="id", how="left"
    )
    entradas = [
        texto_para_modelo(t, lf, x, n)
        for t, lf, x, n in zip(
            base["titulo"], base["linha_fina"], base["texto"], base["nivel_texto"]
        )
    ]
    saidas = base[["id", "titulo", "relevante", "tom"]].copy()
    rotulado_rel = saidas["relevante"] != ""
    rotulado_tom = (saidas["relevante"] == "sim") & (saidas["tom"] != "")
    if not rotulado_rel.any():
        logger.warning(
            "Planilha de rótulos vazia: só o custo será medido, sem acurácia."
        )

    def executar(modelo, texto):
        return (
            modelo.avaliar_hipotese(
                texto, catalogo.HIPOTESE_RELEVANCIA, catalogo.LIMIAR_RELEVANCIA
            ),
            modelo.classificar(texto, catalogo.HIPOTESES_TOM),
        )

    linhas = []
    for config in configs:
        logger.info("Classificação — %s (%d notícias)", config.chave, len(base))
        medicao = medir(config, dispositivo, entradas, executar, fabrica)
        custo = medicao.custo()
        if medicao.erro:
            linhas.append({"tarefa": "relevancia+tom", **custo})
            continue

        relevancia = ["sim" if r.relevante else "nao" for r, _ in medicao.saidas]
        tom = [t.rotulo for _, t in medicao.saidas]
        saidas[f"{config.chave}_relevancia_prob"] = [
            r.probabilidade for r, _ in medicao.saidas
        ]
        saidas[f"{config.chave}_relevante"] = relevancia
        saidas[f"{config.chave}_tom"] = tom
        saidas[f"{config.chave}_tom_confianca"] = [
            t.confianca for _, t in medicao.saidas
        ]
        truncados = round(
            100 * statistics.mean(t.truncado for _, t in medicao.saidas), 1
        )

        for tarefa, coluna, mascara, previsto, classes in (
            ("relevancia", "relevante", rotulado_rel, relevancia, ["sim", "nao"]),
            ("tom", "tom", rotulado_tom, tom, list(catalogo.ROTULOS_TOM)),
        ):
            verdade = saidas.loc[mascara, coluna].tolist()
            prev = [p for p, m in zip(previsto, mascara) if m]
            linha = {
                "tarefa": tarefa,
                **custo,
                "n_itens": len(verdade),
                "truncados_pct": truncados,
            }
            if verdade:
                linha["acuracia"] = round(metricas.acuracia(verdade, prev), 3)
                linha["f1_macro"] = round(metricas.f1_macro(verdade, prev, classes), 3)
            linhas.append(linha)
    return linhas, saidas


# ═══════════════════ Execução ═══════════════════

ORDEM_COLUNAS = [
    "tarefa",
    "modelo",
    "dispositivo",
    "n_itens",
    "rouge1",
    "rougeL",
    "palavras_media",
    "acuracia",
    "f1_macro",
    "truncados_pct",
    "parametros_m",
    "carga_s",
    "tempo_medio_s",
    "tempo_p95_s",
    "ram_processo_mb",
    "vram_pico_mb",
    "licenca",
    "hf_id",
    "erro",
]


def executar_benchmark(
    tarefa: str = "todas",
    dispositivo: str | None = None,
    modelos: list[str] | None = None,
    incluir_generativo: bool = False,
    limite: int | None = None,
    pasta_saida: Path = PASTA_BENCHMARK,
) -> pd.DataFrame:
    from src.ia.modelos_hf import descrever_dispositivo, escolher_dispositivo

    dispositivo = escolher_dispositivo(dispositivo)
    logger.info("Dispositivo: %s", descrever_dispositivo(dispositivo))
    corpus = dados.carregar_corpus()
    pasta_saida.mkdir(parents=True, exist_ok=True)

    def escolher(t: Tarefa) -> list[ModeloConfig]:
        candidatos = catalogo.candidatos_da_tarefa(
            t, incluir_generativo or bool(modelos)
        )
        return [c for c in candidatos if not modelos or c.chave in modelos]

    linhas: list[dict] = []
    if tarefa in {"resumo", "todas"}:
        amostra = amostra_resumo(corpus, limite)
        logger.info(
            "Resumo: %d notícias com linha fina própria como referência.", len(amostra)
        )
        resultado, saidas = avaliar_resumo(
            escolher(Tarefa.resumo), dispositivo, amostra
        )
        linhas += resultado
        saidas.to_csv(
            pasta_saida / f"saidas_resumo_{dispositivo}.csv",
            sep=";",
            index=False,
            encoding="utf-8-sig",
        )

    if tarefa in {"classificacao", "todas"}:
        rotulos = carregar_rotulos()
        rotulos = rotulos.head(limite) if limite else rotulos
        resultado, saidas = avaliar_classificacao(
            escolher(Tarefa.tom), dispositivo, rotulos, corpus
        )
        linhas += resultado
        saidas.to_csv(
            pasta_saida / f"saidas_classificacao_{dispositivo}.csv",
            sep=";",
            index=False,
            encoding="utf-8-sig",
        )

    tabela = pd.DataFrame(linhas)
    tabela = tabela[[c for c in ORDEM_COLUNAS if c in tabela.columns]]
    tabela.to_csv(
        pasta_saida / f"resultados_{dispositivo}.csv",
        sep=";",
        index=False,
        encoding="utf-8-sig",
    )
    return tabela


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark dos modelos locais do SolarGap."
    )
    parser.add_argument(
        "--tarefa", choices=["resumo", "classificacao", "todas"], default="todas"
    )
    parser.add_argument(
        "--dispositivo", choices=["auto", "cuda", "cpu"], default="auto"
    )
    parser.add_argument("--modelos", help="chaves do catálogo separadas por vírgula")
    parser.add_argument("--incluir-generativo", action="store_true")
    parser.add_argument(
        "--limite", type=int, help="usa só as N primeiras notícias (teste rápido)"
    )
    args = parser.parse_args()

    caminho_log = configurar_logging("BENCHMARK_IA", PASTA_LOGS)
    tabela = executar_benchmark(
        tarefa=args.tarefa,
        dispositivo=args.dispositivo,
        modelos=args.modelos.split(",") if args.modelos else None,
        incluir_generativo=args.incluir_generativo,
        limite=args.limite,
    )
    colunas = [
        c
        for c in [
            "tarefa",
            "modelo",
            "rouge1",
            "rougeL",
            "acuracia",
            "f1_macro",
            "tempo_medio_s",
            "vram_pico_mb",
            "erro",
        ]
        if c in tabela.columns
    ]
    print("\n" + tabela[colunas].to_string(index=False))
    logger.info("Resultados em %s | log: %s", PASTA_BENCHMARK, caminho_log)


if __name__ == "__main__":
    main()
