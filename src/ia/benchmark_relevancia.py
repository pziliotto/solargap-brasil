"""
PROJETO: SolarGap Brasil
ARQUIVO: benchmark_relevancia.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Benchmark v2 da relevância (Tarefa 5a): compara estratégias zero-shot num
    conjunto de DESENVOLVIMENTO e avalia a escolhida UMA vez num conjunto de
    TESTE congelado. Reavalia também o tom contra a linha de base.

GABARITO:
    rotulos_benchmark.csv (v1, 30 notícias) + rotulos_benchmark_v2_pendentes.csv
    (v2, 120 notícias, rotuladas pela autora), sem as 2 notícias do v1
    descobertas por caminho proibido pelo robots.txt (rotulagem.IDS_FORA_V2).

DIVISÃO (etapa "dividir", executada uma única vez):
    40% desenvolvimento e 60% teste, estratificada por rótulo de relevância,
    fonte e flag "GD sem solar", com semente fixa. Em cada estrato, a parte
    do desenvolvimento é proporcional; os arredondamentos são resolvidos pelo
    método dos maiores restos, para que o total dê exatamente 40%.
    O teste vai para docs/benchmark/teste_real_congelado.csv e nunca é
    sobrescrito: o SHA-256 do arquivo é conferido por um teste automatizado.

ESTRATÉGIAS DE RELEVÂNCIA (etapa "desenvolvimento"):
    atual      hipótese do TP4: "Esta notícia trata de energia solar."
    ampla      uma hipótese que cita solar, geração distribuída e micro e minigeração
    curtas     três hipóteses curtas (solar, GD, Lei 14.300/compensação); vale a maior
    hibrido_*  termo de GD do vocabulário (no título ou em qualquer campo)
               OU a hipótese atual acima do limiar
    Limiares de 0,30 a 0,70, de 0,05 em 0,05. Métricas da classe "sim":
    precisão, recall e F1, no geral, por fonte e no subconjunto GD sem "solar".

REGRA DE ESCOLHA (definida antes de olhar o teste):
    1. maior F1 geral no desenvolvimento;
    2. empate (diferença < 0,005): maior F1 no subconjunto GD sem "solar";
    3. persistindo: a estratégia mais barata (atual/ampla/híbrido = 1
       inferência; curtas = 3) e o limiar mais perto de 0,5.
    A nova configuração só substitui a atual se, no teste, o F1 geral for
    maior e o IC 95% da diferença pareada (bootstrap) ficar acima de zero.

OBS. DE USO (a partir da raiz):
    python -m src.ia.benchmark_relevancia dividir
    python -m src.ia.benchmark_relevancia desenvolvimento
    python -m src.ia.benchmark_relevancia teste      # uma única vez
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.data_acquisition.coletor_base import obter_project_root
from src.ia import catalogo, metricas, rotulagem
from src.ia.benchmark import _normalizar
from src.servicos import dados
from src.servicos.texto import texto_para_modelo

PROJECT_ROOT = obter_project_root(__file__)
PASTA_BENCHMARK = PROJECT_ROOT / "docs" / "benchmark"
ARQUIVO_V1 = PASTA_BENCHMARK / "rotulos_benchmark.csv"
ARQUIVO_V2 = PASTA_BENCHMARK / "rotulos_benchmark_v2_pendentes.csv"
ARQUIVO_DEV = PASTA_BENCHMARK / "desenvolvimento_real.csv"
ARQUIVO_TESTE = PASTA_BENCHMARK / "teste_real_congelado.csv"
ARQUIVO_PROB_DEV = PASTA_BENCHMARK / "relevancia_probabilidades_dev.csv"
ARQUIVO_GRADE_DEV = PASTA_BENCHMARK / "relevancia_desenvolvimento.csv"
ARQUIVO_ESCOLHA = PASTA_BENCHMARK / "relevancia_escolha.json"
ARQUIVO_TESTE_RESULTADO = PASTA_BENCHMARK / "resultado_teste_congelado.json"
ARQUIVO_TESTE_SAIDAS = PASTA_BENCHMARK / "saidas_teste_congelado.csv"

SEMENTE = 42
FRACAO_DEV = 0.4
REAMOSTRAGENS = 1000
LIMIARES = tuple(round(x, 2) for x in np.arange(0.30, 0.701, 0.05))
COLUNAS_GABARITO = [
    "id",
    "origem",
    "fonte",
    "titulo",
    "url",
    "gd_sem_solar",
    "relevante",
    "tom",
]

logger = logging.getLogger(__name__)

# ═══════════════════ Gabarito e divisão ═══════════════════


def _ler(caminho: Path) -> pd.DataFrame:
    return pd.read_csv(caminho, sep=";", dtype=str, encoding="utf-8-sig").fillna("")


def montar_gabarito(corpus: pd.DataFrame) -> pd.DataFrame:
    """v1 + v2, rótulos padronizados (sim/nao; favoravel/desfavoravel/neutro)."""
    v1 = _ler(ARQUIVO_V1).assign(origem="v1")
    v2 = _ler(ARQUIVO_V2).assign(origem="v2")
    gabarito = pd.concat([v1, v2], ignore_index=True)
    gabarito = gabarito[~gabarito["id"].isin(rotulagem.IDS_FORA_V2)]
    if gabarito["id"].duplicated().any():
        raise ValueError("Notícia repetida entre v1 e v2.")

    gabarito["relevante"] = (
        gabarito["relevante"].map(_normalizar).replace({"s": "sim", "n": "nao"})
    )
    gabarito["tom"] = gabarito["tom"].map(_normalizar)
    invalidos = gabarito[
        ~gabarito["relevante"].isin(["sim", "nao"])
        | ~gabarito["tom"].isin([*catalogo.ROTULOS_TOM, ""])
        | ((gabarito["relevante"] == "sim") != (gabarito["tom"] != ""))
    ]
    if not invalidos.empty:
        raise ValueError(
            f"Rótulos incompletos ou inválidos: {invalidos['id'].tolist()}"
        )

    # Flag recalculada a partir do corpus, igual para v1 e v2.
    textos = corpus.set_index("id").reindex(gabarito["id"])
    if textos["titulo"].isna().any():
        faltam = gabarito.loc[textos["titulo"].isna().to_numpy(), "id"].tolist()
        raise ValueError(f"Notícias do gabarito ausentes do corpus: {faltam}")
    gabarito["gd_sem_solar"] = [
        rotulagem.gd_sem_solar(rotulagem._texto_completo(linha))
        for _, linha in textos.iterrows()
    ]
    gabarito["fonte"] = textos["fonte"].to_numpy()
    gabarito["titulo"] = textos["titulo"].to_numpy()
    gabarito["url"] = textos["url"].to_numpy()
    return gabarito[COLUNAS_GABARITO].sort_values("id").reset_index(drop=True)


def dividir(
    gabarito: pd.DataFrame, fracao_dev: float = FRACAO_DEV, semente: int = SEMENTE
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Divisão estratificada (relevante x fonte x gd_sem_solar), maiores restos."""
    estratos = gabarito.groupby(["relevante", "fonte", "gd_sem_solar"]).size()
    ideal = estratos * fracao_dev
    cota = np.floor(ideal).astype(int)
    faltam = round(len(gabarito) * fracao_dev) - int(cota.sum())
    restos = (ideal - cota).sort_values(ascending=False, kind="stable")
    for chave in restos.index[:faltam]:
        cota[chave] += 1

    gerador = np.random.default_rng(semente)
    ids_dev: list[str] = []
    for chave, quantidade in cota.items():
        r, f, g = chave
        grupo = gabarito[
            (gabarito["relevante"] == r)
            & (gabarito["fonte"] == f)
            & (gabarito["gd_sem_solar"] == g)
        ]["id"].sort_values()
        ids_dev += gerador.choice(
            grupo.to_numpy(), size=quantidade, replace=False
        ).tolist()

    dev = gabarito[gabarito["id"].isin(ids_dev)].reset_index(drop=True)
    teste = gabarito[~gabarito["id"].isin(ids_dev)].reset_index(drop=True)
    return dev, teste


def sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def congelar(corpus: pd.DataFrame) -> tuple[Path, Path]:
    """Etapa 'dividir': grava desenvolvimento e teste. Nunca sobrescreve o teste."""
    if ARQUIVO_TESTE.exists():
        raise SystemExit(
            f"{ARQUIVO_TESTE.name} já existe e está congelado; nada foi alterado."
        )
    dev, teste = dividir(montar_gabarito(corpus))
    for tabela, destino in ((dev, ARQUIVO_DEV), (teste, ARQUIVO_TESTE)):
        tabela.to_csv(destino, sep=";", index=False, encoding="utf-8-sig")
    logger.info(
        "Desenvolvimento: %d | teste congelado: %d | SHA-256 do teste: %s",
        len(dev),
        len(teste),
        sha256(ARQUIVO_TESTE),
    )
    return ARQUIVO_DEV, ARQUIVO_TESTE


def ler_conjunto(caminho: Path) -> pd.DataFrame:
    tabela = _ler(caminho)
    tabela["gd_sem_solar"] = tabela["gd_sem_solar"] == "True"
    return tabela


# ═══════════════════ Hipóteses e estratégias ═══════════════════

HIPOTESES = {
    "atual": catalogo.HIPOTESE_RELEVANCIA,
    "ampla": (
        "Esta notícia trata de energia solar, geração distribuída ou micro e "
        "minigeração de energia."
    ),
    "gd": "Esta notícia trata de geração distribuída de energia.",
    "lei": "Esta notícia trata da Lei 14.300 ou da compensação de energia elétrica.",
}
CURTAS = ("atual", "gd", "lei")  # "atual" é a hipótese curta de energia solar


def termo_gd(texto: str) -> bool:
    """Menciona termo do vocabulário de GD (Lei 14.300, fio B, micro/minigeração...)."""
    return rotulagem.palavra_chave(texto) in rotulagem.PALAVRAS_GD


@dataclass(frozen=True)
class Estrategia:
    nome: str
    descricao: str
    inferencias: int  # chamadas ao modelo por notícia (custo)
    pontuar: Callable[[pd.DataFrame], pd.Series]  # probabilidade usada no limiar
    forcar_sim: Callable[[pd.DataFrame], pd.Series] | None = None  # regra de palavra

    def prever(self, base: pd.DataFrame, limiar: float) -> pd.Series:
        sim = self.pontuar(base) >= limiar
        if self.forcar_sim is not None:
            sim = sim | self.forcar_sim(base)
        return sim.map({True: "sim", False: "nao"})


ESTRATEGIAS = {
    e.nome: e
    for e in (
        Estrategia("atual", "hipótese atual (TP4)", 1, lambda b: b["p_atual"]),
        Estrategia("ampla", "hipótese ampla", 1, lambda b: b["p_ampla"]),
        Estrategia(
            "curtas",
            "máximo de 3 hipóteses curtas",
            3,
            lambda b: b[[f"p_{h}" for h in CURTAS]].max(axis=1),
        ),
        Estrategia(
            "hibrido_titulo",
            "termo de GD no título OU hipótese atual",
            1,
            lambda b: b["p_atual"],
            lambda b: b["gd_no_titulo"],
        ),
        Estrategia(
            "hibrido_texto",
            "termo de GD em qualquer campo OU hipótese atual",
            1,
            lambda b: b["p_atual"],
            lambda b: b["gd_no_texto"],
        ),
    )
}


# ═══════════════════ Probabilidades (modelo) ═══════════════════


def entradas(conjunto: pd.DataFrame, corpus: pd.DataFrame) -> pd.DataFrame:
    base = conjunto.merge(
        corpus[["id", "linha_fina", "texto", "nivel_texto"]], on="id", how="left"
    )
    base["entrada"] = [
        texto_para_modelo(t, lf, x, n)
        for t, lf, x, n in zip(
            base["titulo"], base["linha_fina"], base["texto"], base["nivel_texto"]
        )
    ]
    completo = [
        " ".join(str(v) for v in (t, lf, x) if isinstance(v, str))
        for t, lf, x in zip(base["titulo"], base["linha_fina"], base["texto"])
    ]
    base["gd_no_titulo"] = base["titulo"].map(termo_gd)
    base["gd_no_texto"] = [termo_gd(t) for t in completo]
    return base


def calcular_probabilidades(base: pd.DataFrame, modelo) -> pd.DataFrame:
    """Uma inferência por notícia e hipótese; o limiar não interfere na probabilidade."""
    saida = base[["id"]].copy()
    for nome, hipotese in HIPOTESES.items():
        saida[f"p_{nome}"] = [
            modelo.avaliar_hipotese(texto, hipotese, 0.5).probabilidade
            for texto in base["entrada"]
        ]
        logger.info("  hipótese '%s' avaliada em %d notícias", nome, len(base))
    return saida


def carregar_modelo(dispositivo: str | None = None):
    from src.ia.modelos_hf import criar_modelo, escolher_dispositivo

    config = catalogo.modelo_da_tarefa(catalogo.Tarefa.relevancia)
    modelo = criar_modelo(config, escolher_dispositivo(dispositivo))
    modelo.carregar()
    return modelo


# ═══════════════════ Métricas ═══════════════════


def prf(verdade: pd.Series, previsto: pd.Series) -> dict:
    """Precisão, recall e F1 da classe 'sim'."""
    vp = int(((verdade == "sim") & (previsto == "sim")).sum())
    fp = int(((verdade == "nao") & (previsto == "sim")).sum())
    fn = int(((verdade == "sim") & (previsto == "nao")).sum())
    precisao = vp / (vp + fp) if vp + fp else 0.0
    recall = vp / (vp + fn) if vp + fn else 0.0
    f1 = 2 * precisao * recall / (precisao + recall) if precisao + recall else 0.0
    return {"n": len(verdade), "precisao": precisao, "recall": recall, "f1": f1}


def recortes(base: pd.DataFrame) -> dict[str, pd.Series]:
    """Máscaras: geral, cada fonte e o subconjunto GD sem 'solar'."""
    mascaras = {"geral": pd.Series(True, index=base.index)}
    for fonte in sorted(base["fonte"].unique()):
        mascaras[f"fonte:{fonte}"] = base["fonte"] == fonte
    mascaras["gd_sem_solar"] = base["gd_sem_solar"]
    return mascaras


def grade_desenvolvimento(base: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for estrategia in ESTRATEGIAS.values():
        for limiar in LIMIARES:
            previsto = estrategia.prever(base, limiar)
            for recorte, mascara in recortes(base).items():
                linhas.append(
                    {
                        "estrategia": estrategia.nome,
                        "limiar": limiar,
                        "recorte": recorte,
                        **prf(base.loc[mascara, "relevante"], previsto[mascara]),
                    }
                )
    grade = pd.DataFrame(linhas)
    for coluna in ("precisao", "recall", "f1"):
        grade[coluna] = grade[coluna].round(3)
    return grade


def escolher(grade: pd.DataFrame) -> dict:
    """Aplica a regra de escolha do cabeçalho."""
    geral = grade[grade["recorte"] == "geral"].set_index(["estrategia", "limiar"])["f1"]
    gd = grade[grade["recorte"] == "gd_sem_solar"].set_index(["estrategia", "limiar"])[
        "f1"
    ]
    candidatos = geral[geral >= geral.max() - 0.005].index
    ordem = sorted(
        candidatos,
        key=lambda c: (
            -gd[c],
            ESTRATEGIAS[c[0]].inferencias,
            abs(c[1] - 0.5),
            c[0],
        ),
    )
    estrategia, limiar = ordem[0]
    return {
        "estrategia": estrategia,
        "limiar": float(limiar),
        "f1_geral_dev": float(geral[(estrategia, limiar)]),
        "f1_gd_sem_solar_dev": float(gd[(estrategia, limiar)]),
        "empatados": [f"{e}@{lim}" for e, lim in candidatos],
    }


def etapa_desenvolvimento(dispositivo: str | None = None) -> dict:
    corpus = dados.carregar_corpus()
    base = entradas(ler_conjunto(ARQUIVO_DEV), corpus)
    if ARQUIVO_PROB_DEV.exists():
        prob = pd.read_csv(ARQUIVO_PROB_DEV, sep=";", dtype={"id": str})
    else:
        prob = calcular_probabilidades(base, carregar_modelo(dispositivo))
        prob.to_csv(ARQUIVO_PROB_DEV, sep=";", index=False, encoding="utf-8-sig")
    base = base.merge(prob, on="id")
    grade = grade_desenvolvimento(base)
    grade.to_csv(ARQUIVO_GRADE_DEV, sep=";", index=False, encoding="utf-8-sig")
    escolha = escolher(grade)
    ARQUIVO_ESCOLHA.write_text(
        json.dumps(escolha, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Escolha no desenvolvimento: %s", escolha)
    return escolha


# ═══════════════════ Teste congelado (uma única vez) ═══════════════════
#
# Condição acrescentada em 22/11/2026, DEPOIS de ver o desenvolvimento e ANTES
# de abrir o teste: no desenvolvimento, a estratégia escolhida acertou só 2
# dos 17 "nao" e ficou a 0,016 de F1 de responder sempre "sim". Como no tom,
# um classificador só é útil se superar a referência trivial. Por isso a
# adoção exige vencer, com IC 95% da diferença pareada acima de zero, tanto a
# configuração atual quanto "sempre sim".


def sempre_sim(base: pd.DataFrame) -> pd.Series:
    return pd.Series("sim", index=base.index)


def _f1(verdade: np.ndarray, previsto: np.ndarray) -> float:
    vp = np.sum((verdade == "sim") & (previsto == "sim"))
    fp = np.sum((verdade == "nao") & (previsto == "sim"))
    fn = np.sum((verdade == "sim") & (previsto == "nao"))
    return float(2 * vp / (2 * vp + fp + fn)) if vp else 0.0


def bootstrap(
    verdade: pd.Series,
    previsoes: dict[str, pd.Series],
    pares: list[tuple[str, str]],
    reamostragens: int = REAMOSTRAGENS,
    semente: int = SEMENTE,
) -> dict:
    """F1 da classe 'sim' com IC 95% (percentis) e diferenças pareadas."""
    v = verdade.to_numpy()
    p = {nome: s.to_numpy() for nome, s in previsoes.items()}
    gerador = np.random.default_rng(semente)
    amostras = {nome: [] for nome in p}
    for _ in range(reamostragens):
        i = gerador.integers(0, len(v), len(v))
        for nome, previsto in p.items():
            amostras[nome].append(_f1(v[i], previsto[i]))

    def ic(valores) -> list[float]:
        return [round(float(np.percentile(valores, q)), 3) for q in (2.5, 97.5)]

    resultado = {"n": len(v), "n_sim": int((v == "sim").sum())}
    for nome, previsto in p.items():
        resultado[nome] = {
            **{
                k: round(x, 3)
                for k, x in prf(verdade, previsoes[nome]).items()
                if k != "n"
            },
            "ic95_f1": ic(amostras[nome]),
        }
    for a, b in pares:
        diferencas = np.array(amostras[a]) - np.array(amostras[b])
        resultado[f"{a}_menos_{b}"] = {
            "diferenca_f1": round(_f1(v, p[a]) - _f1(v, p[b]), 3),
            "ic95": ic(diferencas),
        }
    return resultado


def avaliar_tom(base: pd.DataFrame, modelo, majoritaria: str) -> dict:
    """Zero-shot do tom contra a linha de base de classe majoritária (F1 macro)."""
    relevantes = base[base["relevante"] == "sim"]
    previsto = [
        modelo.classificar(texto, catalogo.HIPOTESES_TOM).rotulo
        for texto in relevantes["entrada"]
    ]
    verdade = relevantes["tom"].tolist()
    classes = list(catalogo.ROTULOS_TOM)
    linha_base = [majoritaria] * len(verdade)
    return {
        "n": len(verdade),
        "distribuicao": relevantes["tom"].value_counts().to_dict(),
        "zero_shot": {
            "f1_macro": round(metricas.f1_macro(verdade, previsto, classes), 3),
            "acuracia": round(metricas.acuracia(verdade, previsto), 3),
        },
        "linha_base": {
            "classe": majoritaria,
            "f1_macro": round(metricas.f1_macro(verdade, linha_base, classes), 3),
            "acuracia": round(metricas.acuracia(verdade, linha_base), 3),
        },
        "previsoes": dict(zip(relevantes["id"], previsto)),
    }


def etapa_teste(dispositivo: str | None = None) -> dict:
    if ARQUIVO_TESTE_RESULTADO.exists():
        raise SystemExit(
            f"O teste congelado já foi usado ({ARQUIVO_TESTE_RESULTADO.name}). "
            "Ele só é avaliado uma vez."
        )
    escolha = json.loads(ARQUIVO_ESCOLHA.read_text(encoding="utf-8"))
    corpus = dados.carregar_corpus()
    modelo = carregar_modelo(dispositivo)
    dev = entradas(ler_conjunto(ARQUIVO_DEV), corpus)
    teste = entradas(ler_conjunto(ARQUIVO_TESTE), corpus)
    teste = teste.merge(calcular_probabilidades(teste, modelo), on="id")

    escolhida = ESTRATEGIAS[escolha["estrategia"]].prever(teste, escolha["limiar"])
    atual = ESTRATEGIAS["atual"].prever(teste, catalogo.LIMIAR_RELEVANCIA)
    previsoes = {
        "escolhida": escolhida,
        "atual": atual,
        "sempre_sim": sempre_sim(teste),
    }
    pares = [
        ("escolhida", "atual"),
        ("escolhida", "sempre_sim"),
        ("atual", "sempre_sim"),
    ]
    gd = teste["gd_sem_solar"]
    relevancia = {
        "geral": bootstrap(teste["relevante"], previsoes, pares),
        "gd_sem_solar": bootstrap(
            teste.loc[gd, "relevante"], {k: v[gd] for k, v in previsoes.items()}, pares
        ),
        "por_fonte": {
            fonte: {
                nome: prf(teste.loc[m, "relevante"], prev[m])
                for nome, prev in previsoes.items()
            }
            for fonte, m in (
                (f, teste["fonte"] == f) for f in sorted(teste["fonte"].unique())
            )
        },
    }
    geral = relevancia["geral"]
    vence = all(
        geral[f"escolhida_menos_{ref}"]["diferenca_f1"] > 0
        and geral[f"escolhida_menos_{ref}"]["ic95"][0] > 0
        for ref in ("atual", "sempre_sim")
    )

    majoritaria = dev.loc[dev["relevante"] == "sim", "tom"].value_counts().idxmax()
    tom_dev = avaliar_tom(dev, modelo, majoritaria)
    tom_teste = avaliar_tom(teste, modelo, majoritaria)

    resultado = {
        "escolha_dev": escolha,
        "configuracao_atual": {
            "estrategia": "atual",
            "limiar": catalogo.LIMIAR_RELEVANCIA,
        },
        "relevancia": relevancia,
        "escolhida_vence": vence,
        "tom": {"desenvolvimento": tom_dev, "teste": tom_teste},
        "sha256_teste": sha256(ARQUIVO_TESTE),
    }
    saidas = teste[["id", "fonte", "gd_sem_solar", "relevante", "tom"]].copy()
    saidas = saidas.join(teste[[c for c in teste.columns if c.startswith("p_")]])
    for nome, prev in previsoes.items():
        saidas[f"prev_{nome}"] = prev
    saidas["tom_zero_shot"] = saidas["id"].map(tom_teste.pop("previsoes"))
    tom_dev.pop("previsoes")
    saidas.to_csv(ARQUIVO_TESTE_SAIDAS, sep=";", index=False, encoding="utf-8-sig")
    ARQUIVO_TESTE_RESULTADO.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Resultado no teste congelado gravado em %s", ARQUIVO_TESTE_RESULTADO)
    return resultado


# ═══════════════════ Correção de métrica: F1 macro (22/11/2026) ═══════════════════
#
# O critério da primeira escolha (F1 da classe "sim") estava errado para este
# corpus: todas as notícias passaram pelo filtro de palavras da coleta, 72%
# são relevantes, e responder sempre "sim" vence o F1-sim quase de graça.
# A escolha foi refeita SÓ no desenvolvimento, com as probabilidades já
# salvas (sem nova inferência), pelo F1 macro das duas classes:
#   1. restrições: F1 macro acima do de "sempre sim" e F1 da classe "sim"
#      maior que zero no subconjunto GD sem "solar";
#   2. critério: maior F1 macro;
#   3. empate (diferença < 0,005): maior precisão da classe "sim"; depois
#      menor custo e limiar mais perto de 0,5.
# Esta é a SEGUNDA consulta ao teste congelado: a primeira (F1-sim) está em
# resultado_teste_congelado.json e não foi alterada. Adoção: F1 macro maior
# que o da atual e o de "sempre sim", com IC 95% da diferença pareada acima
# de zero nos dois casos.

ARQUIVO_GRADE_DEV_V2 = PASTA_BENCHMARK / "relevancia_desenvolvimento_v2.csv"
ARQUIVO_ESCOLHA_V2 = PASTA_BENCHMARK / "relevancia_escolha_v2.json"
ARQUIVO_TESTE_RESULTADO_V2 = PASTA_BENCHMARK / "resultado_teste_congelado_v2.json"
TOLERANCIA_EMPATE = 0.005


def metricas_duas_classes(verdade: pd.Series, previsto: pd.Series) -> dict:
    """Precisão, recall e F1 de 'sim' e de 'nao', e o F1 macro."""
    v, p = verdade.to_numpy(), previsto.to_numpy()
    saida: dict = {"n": len(v)}
    for classe in ("sim", "nao"):
        vp = int(np.sum((v == classe) & (p == classe)))
        fp = int(np.sum((v != classe) & (p == classe)))
        fn = int(np.sum((v == classe) & (p != classe)))
        precisao = vp / (vp + fp) if vp + fp else 0.0
        recall = vp / (vp + fn) if vp + fn else 0.0
        f1 = 2 * precisao * recall / (precisao + recall) if precisao + recall else 0.0
        saida |= {
            f"precisao_{classe}": precisao,
            f"recall_{classe}": recall,
            f"f1_{classe}": f1,
        }
    saida["f1_macro"] = (saida["f1_sim"] + saida["f1_nao"]) / 2
    return saida


def _f1_macro(v: np.ndarray, p: np.ndarray) -> float:
    valores = []
    for classe in ("sim", "nao"):
        vp = np.sum((v == classe) & (p == classe))
        erros = np.sum((v != classe) & (p == classe)) + np.sum(
            (v == classe) & (p != classe)
        )
        valores.append(float(2 * vp / (2 * vp + erros)) if vp else 0.0)
    return sum(valores) / 2


def configuracoes(base: pd.DataFrame) -> dict[tuple[str, float | None], pd.Series]:
    """Todas as previsões do desenvolvimento, inclusive a referência 'sempre sim'."""
    saida = {("sempre_sim", None): sempre_sim(base)}
    for estrategia in ESTRATEGIAS.values():
        for limiar in LIMIARES:
            saida[(estrategia.nome, limiar)] = estrategia.prever(base, limiar)
    return saida


def grade_macro(base: pd.DataFrame) -> pd.DataFrame:
    gd = base["gd_sem_solar"]
    linhas = []
    for (estrategia, limiar), previsto in configuracoes(base).items():
        geral = metricas_duas_classes(base["relevante"], previsto)
        no_gd = metricas_duas_classes(base.loc[gd, "relevante"], previsto[gd])
        linhas.append(
            {
                "estrategia": estrategia,
                "limiar": limiar,
                **{k: v for k, v in geral.items() if k != "n"},
                "f1_sim_gd_sem_solar": no_gd["f1_sim"],
                "f1_macro_gd_sem_solar": no_gd["f1_macro"],
            }
        )
    grade = pd.DataFrame(linhas)
    numericas = grade.columns.drop(["estrategia", "limiar"])
    grade[numericas] = grade[numericas].round(3)
    return grade


def escolher_macro(grade: pd.DataFrame) -> dict:
    referencia = grade.loc[grade["estrategia"] == "sempre_sim", "f1_macro"].iloc[0]
    validas = grade[
        (grade["estrategia"] != "sempre_sim")
        & (grade["f1_macro"] > referencia)
        & (grade["f1_sim_gd_sem_solar"] > 0)
    ]
    if validas.empty:
        return {
            "estrategia": None,
            "motivo": "nenhuma configuração cumpre as restrições",
        }
    empatadas = validas[
        validas["f1_macro"] >= validas["f1_macro"].max() - TOLERANCIA_EMPATE
    ]
    ordem = empatadas.assign(
        custo=empatadas["estrategia"].map(lambda e: ESTRATEGIAS[e].inferencias),
        distancia=(empatadas["limiar"] - 0.5).abs(),
    ).sort_values(
        ["precisao_sim", "custo", "distancia", "estrategia"],
        ascending=[False, True, True, True],
    )
    melhor = ordem.iloc[0]
    return {
        "estrategia": melhor["estrategia"],
        "limiar": float(melhor["limiar"]),
        "f1_macro_dev": float(melhor["f1_macro"]),
        "precisao_sim_dev": float(melhor["precisao_sim"]),
        "f1_sim_gd_sem_solar_dev": float(melhor["f1_sim_gd_sem_solar"]),
        "f1_macro_sempre_sim_dev": float(referencia),
        "empatadas": [
            f"{e}@{lim}" for e, lim in zip(empatadas["estrategia"], empatadas["limiar"])
        ],
        "regra": (
            "restrições: F1 macro > 'sempre sim' e F1-sim > 0 em GD sem solar; critério: maior "
            "F1 macro; empate (< 0,005): maior precisão de 'sim', menor custo, limiar mais perto de 0,5"
        ),
        "condicao_de_adocao": (
            "no teste, F1 macro maior que o da configuração atual e o de 'sempre sim', com IC 95% "
            "da diferença pareada acima de zero nos dois casos"
        ),
    }


def etapa_desenvolvimento_v2() -> dict:
    """Reescolha pelo F1 macro com as probabilidades salvas: nenhuma inferência."""
    base = entradas(ler_conjunto(ARQUIVO_DEV), dados.carregar_corpus())
    prob = pd.read_csv(
        ARQUIVO_PROB_DEV, sep=";", dtype={"id": str}, encoding="utf-8-sig"
    )
    base = base.merge(prob, on="id")
    grade = grade_macro(base)
    grade.to_csv(ARQUIVO_GRADE_DEV_V2, sep=";", index=False, encoding="utf-8-sig")
    escolha = escolher_macro(grade)
    ARQUIVO_ESCOLHA_V2.write_text(
        json.dumps(escolha, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Escolha pelo F1 macro: %s", escolha)
    return escolha


def bootstrap_macro(
    verdade: pd.Series,
    previsoes: dict[str, pd.Series],
    pares: list[tuple[str, str]],
    reamostragens: int = REAMOSTRAGENS,
    semente: int = SEMENTE,
) -> dict:
    """F1 macro com IC 95% (percentis) e diferenças pareadas nas mesmas reamostragens."""
    v = verdade.to_numpy()
    p = {nome: s.to_numpy() for nome, s in previsoes.items()}
    gerador = np.random.default_rng(semente)
    amostras = {nome: [] for nome in p}
    for _ in range(reamostragens):
        i = gerador.integers(0, len(v), len(v))
        for nome, previsto in p.items():
            amostras[nome].append(_f1_macro(v[i], previsto[i]))

    def ic(valores) -> list[float]:
        return [round(float(np.percentile(valores, q)), 3) for q in (2.5, 97.5)]

    resultado = {"n": len(v), "n_sim": int((v == "sim").sum())}
    for nome in p:
        metricas_ = metricas_duas_classes(verdade, previsoes[nome])
        resultado[nome] = {
            **{k: round(x, 3) for k, x in metricas_.items() if k != "n"},
            "ic95_f1_macro": ic(amostras[nome]),
        }
    for a, b in pares:
        diferencas = np.array(amostras[a]) - np.array(amostras[b])
        resultado[f"{a}_menos_{b}"] = {
            "diferenca_f1_macro": round(_f1_macro(v, p[a]) - _f1_macro(v, p[b]), 3),
            "ic95": ic(diferencas),
        }
    return resultado


def etapa_teste_v2() -> dict:
    """SEGUNDA consulta ao teste congelado, com as probabilidades da primeira (sem inferência)."""
    if ARQUIVO_TESTE_RESULTADO_V2.exists():
        raise SystemExit(
            f"A segunda consulta ao teste já foi feita ({ARQUIVO_TESTE_RESULTADO_V2.name})."
        )
    escolha = json.loads(ARQUIVO_ESCOLHA_V2.read_text(encoding="utf-8"))
    if not escolha.get("estrategia"):
        raise SystemExit(
            "Nenhuma configuração passou nas restrições do desenvolvimento."
        )
    teste = entradas(ler_conjunto(ARQUIVO_TESTE), dados.carregar_corpus())
    prob = pd.read_csv(
        ARQUIVO_TESTE_SAIDAS, sep=";", dtype={"id": str}, encoding="utf-8-sig"
    )
    teste = teste.merge(
        prob[["id", *[c for c in prob.columns if c.startswith("p_")]]], on="id"
    )
    if len(teste) != len(ler_conjunto(ARQUIVO_TESTE)):
        raise ValueError("Probabilidades do teste incompletas.")

    previsoes = {
        "escolhida_v2": ESTRATEGIAS[escolha["estrategia"]].prever(
            teste, escolha["limiar"]
        ),
        "atual": ESTRATEGIAS["atual"].prever(teste, catalogo.LIMIAR_RELEVANCIA),
        "sempre_sim": sempre_sim(teste),
    }
    pares = [
        ("escolhida_v2", "atual"),
        ("escolhida_v2", "sempre_sim"),
        ("atual", "sempre_sim"),
    ]
    gd = teste["gd_sem_solar"]
    geral = bootstrap_macro(teste["relevante"], previsoes, pares)
    vence = all(
        geral[f"escolhida_v2_menos_{ref}"]["diferenca_f1_macro"] > 0
        and geral[f"escolhida_v2_menos_{ref}"]["ic95"][0] > 0
        for ref in ("atual", "sempre_sim")
    )
    resultado = {
        "consulta": 2,
        "aviso": (
            "Segunda consulta ao teste congelado, feita depois de corrigir a métrica de escolha "
            "(F1-sim para F1 macro). A evidência é mais fraca que a de uma consulta única."
        ),
        "escolha_dev_v2": escolha,
        "relevancia": {
            "geral": geral,
            "gd_sem_solar": bootstrap_macro(
                teste.loc[gd, "relevante"],
                {k: v[gd] for k, v in previsoes.items()},
                pares,
            ),
            "por_fonte": {
                fonte: {
                    nome: {
                        k: round(x, 3)
                        for k, x in metricas_duas_classes(
                            teste.loc[teste["fonte"] == fonte, "relevante"],
                            prev[teste["fonte"] == fonte],
                        ).items()
                    }
                    for nome, prev in previsoes.items()
                }
                for fonte in sorted(teste["fonte"].unique())
            },
        },
        "escolhida_vence": vence,
        "sha256_teste": sha256(ARQUIVO_TESTE),
    }
    ARQUIVO_TESTE_RESULTADO_V2.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Segunda consulta gravada em %s", ARQUIVO_TESTE_RESULTADO_V2)
    return resultado


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    for barulhento in ("httpx", "huggingface_hub", "urllib3"):
        logging.getLogger(barulhento).setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description="Benchmark v2 da relevância e do tom.")
    parser.add_argument(
        "etapa",
        choices=[
            "dividir",
            "desenvolvimento",
            "teste",
            "desenvolvimento_v2",
            "teste_v2",
        ],
    )
    parser.add_argument("--dispositivo", choices=["cuda", "cpu"], default=None)
    argumentos = parser.parse_args()
    if argumentos.etapa == "dividir":
        congelar(dados.carregar_corpus())
    elif argumentos.etapa == "desenvolvimento":
        etapa_desenvolvimento(argumentos.dispositivo)
    elif argumentos.etapa == "desenvolvimento_v2":
        etapa_desenvolvimento_v2()
    elif argumentos.etapa == "teste_v2":
        etapa_teste_v2()
    else:
        etapa_teste(argumentos.dispositivo)


if __name__ == "__main__":
    main()
