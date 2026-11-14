"""
PROJETO: SolarGap Brasil
ARQUIVO: metricas.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 13/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Métricas do benchmark, implementadas aqui em poucas linhas.

POR QUE NÃO USAR O PACOTE rouge-score:
    O tokenizador dele descarta tudo que não é [a-z0-9]: "geração" vira "gera"
    + "o" e "energia elétrica" perde o acento. Em português isso distorce a
    métrica. Aqui a tokenização usa \\w do Python, que reconhece letras
    acentuadas.

    ROUGE-1  sobreposição de palavras entre o resumo gerado e a referência
    ROUGE-L  maior subsequência comum (premia a mesma ordem das ideias)
    Ambas devolvem F1, entre 0 e 1.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence


def tokenizar(texto: str | None) -> list[str]:
    return re.findall(r"\w+", (texto or "").lower())


def _f1(acertos: float, total_candidato: int, total_referencia: int) -> float:
    if not acertos or not total_candidato or not total_referencia:
        return 0.0
    precisao = acertos / total_candidato
    revocacao = acertos / total_referencia
    return 2 * precisao * revocacao / (precisao + revocacao)


def rouge_1(candidato: str, referencia: str) -> float:
    c, r = Counter(tokenizar(candidato)), Counter(tokenizar(referencia))
    return _f1(sum((c & r).values()), sum(c.values()), sum(r.values()))


def _lcs(a: Sequence[str], b: Sequence[str]) -> int:
    anterior = [0] * (len(b) + 1)
    for x in a:
        atual = [0]
        for j, y in enumerate(b, start=1):
            atual.append(
                anterior[j - 1] + 1 if x == y else max(anterior[j], atual[j - 1])
            )
        anterior = atual
    return anterior[-1]


def rouge_l(candidato: str, referencia: str) -> float:
    c, r = tokenizar(candidato), tokenizar(referencia)
    return _f1(_lcs(c, r), len(c), len(r))


def acuracia(verdade: Sequence[str], previsto: Sequence[str]) -> float:
    if not verdade:
        return 0.0
    return sum(v == p for v, p in zip(verdade, previsto)) / len(verdade)


def f1_macro(
    verdade: Sequence[str], previsto: Sequence[str], rotulos: Sequence[str]
) -> float:
    """Média simples do F1 de cada classe — não deixa a classe mais frequente mascarar as demais."""
    valores = []
    for rotulo in rotulos:
        vp = sum(v == rotulo and p == rotulo for v, p in zip(verdade, previsto))
        fp = sum(v != rotulo and p == rotulo for v, p in zip(verdade, previsto))
        fn = sum(v == rotulo and p != rotulo for v, p in zip(verdade, previsto))
        valores.append(_f1(vp, vp + fp, vp + fn))
    return sum(valores) / len(valores) if valores else 0.0
