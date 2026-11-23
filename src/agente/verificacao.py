"""
PROJETO: SolarGap Brasil
ARQUIVO: agente/verificacao.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026 (TP5)

DESCRIÇÃO:
    Confere se cada número da resposta do agente aparece nos fatos devolvidos
    pelas ferramentas (ou na própria pergunta). É a defesa contra a
    "alucinação numérica", o risco central de um LLM num projeto cujo valor é
    o dado validado.

COMO:
    Extrai números no formato pt-BR (9,0 · 603,4 · 184.843 · -7,7) e compara
    com o conjunto de números dos fatos. Ignora números de lista ("1.") e
    referências fixas que não são medida: anos de 1990 a 2060, "14.300" (a
    lei), siglas de cenário (SSP2-4.5 vira "2", "4,5": aceitos se estiverem
    nos fatos).

SAÍDA:
    {"numeros": n, "verificados": k, "nao_encontrados": [...], "taxa": k/n}
    A página do agente mostra um selo verde (100%) ou um aviso com os números
    que não vieram dos dados.
"""

from __future__ import annotations

import re

_NUMERO = re.compile(
    r"(?<![\w])[-−]?\d{1,3}(?:\.\d{3})+(?:,\d+)?|(?<![\w])[-−]?\d+(?:,\d+)?"
)
IGNORAR = {"14.300", "14300"}


def _normalizar(token: str) -> str:
    return token.replace("−", "-").lstrip("+")


def extrair_numeros(texto: str) -> list[str]:
    numeros = []
    for achado in _NUMERO.finditer(texto):
        token = _normalizar(achado.group(0))
        fim = achado.end()
        # item de lista numerada ("1. ") ou ordinal ("1º")
        if (
            texto[fim : fim + 2] in (". ", ".\n")
            and "," not in token
            and len(token) <= 2
        ):
            continue
        if texto[fim : fim + 1] in ("º", "ª", "°"):  # ordinal ("1º lugar")
            continue
        if token in IGNORAR:
            continue
        sem_sinal = token.lstrip("-")
        if sem_sinal.isdigit() and 1990 <= int(sem_sinal) <= 2060:
            continue
        numeros.append(token)
    return numeros


def verificar(resposta: str, fatos: list[str], pergunta: str = "") -> dict:
    referencia = set()
    for texto in [*fatos, pergunta]:
        for n in extrair_numeros(texto):
            referencia.add(n)
            referencia.add(n.lstrip("-"))  # "-7,7 p.p." pode virar "reduz 7,7 p.p."
    numeros = extrair_numeros(resposta)
    nao_encontrados = [
        n for n in numeros if n not in referencia and n.lstrip("-") not in referencia
    ]
    verificados = len(numeros) - len(nao_encontrados)
    return {
        "numeros": len(numeros),
        "verificados": verificados,
        "nao_encontrados": list(dict.fromkeys(nao_encontrados)),
        "taxa": 1.0 if not numeros else verificados / len(numeros),
    }


# Rótulos que o LLM trocou na rodada 2: chamou o gap total (603,4 GWh/ano) de
# "gap acima do esperado" (12,2 GWh/ano). O número existia nos dados, então a
# checagem de números não pegava. Aqui o número tem de aparecer COLADO ao mesmo
# rótulo em algum fato.
ROTULOS = ("acima do esperado",)
# Só energia e pontos percentuais: o gap acima do esperado nunca é uma taxa em %
# (o 12,6% da taxa esperada de Pará de Minas, colado ao rótulo, era falso alarme).
_MEDIDA = re.compile(
    rf"({_NUMERO.pattern})\s*(?:[TGMk]Wh|p\.\s?p\.|pontos?\s+percentua(?:l|is))",
    re.IGNORECASE,
)
JANELA = 30  # caracteres entre o rótulo e o número


def _numeros_colados(texto: str, rotulo: str) -> list[tuple[str, int]]:
    """Números imediatamente antes ou depois de cada ocorrência do rótulo."""
    achados = []
    minusculo = texto.lower()
    for ocorrencia in re.finditer(re.escape(rotulo), minusculo):
        depois = texto[ocorrencia.end() : ocorrencia.end() + JANELA]
        antes = texto[max(0, ocorrencia.start() - JANELA) : ocorrencia.start()]
        # a janela não atravessa o fim da frase ou do item
        depois = re.split(r"\n|; |\. ", depois, maxsplit=1)[0]
        antes = re.split(r"\n|; |\. ", antes)[-1]
        # só medidas (energia e pontos percentuais): contagens como "66 municípios com gap
        # acima do esperado" não são o valor do gap (falso alarme da rodada 3)
        n_depois = [_normalizar(m.group(1)) for m in _MEDIDA.finditer(depois)]
        n_antes = [_normalizar(m.group(1)) for m in _MEDIDA.finditer(antes)]
        if n_depois:
            achados.append((n_depois[0], ocorrencia.start()))
        if n_antes:
            achados.append((n_antes[-1], ocorrencia.start()))
    return achados


def verificar_rotulos(resposta: str, fatos: list[str]) -> list[tuple[str, str]]:
    """Pares (rótulo, número) da resposta que nenhum fato traz com esse rótulo."""
    problemas = []
    for rotulo in ROTULOS:
        validos = {n for fato in fatos for n, _ in _numeros_colados(fato, rotulo)}
        for numero, _ in _numeros_colados(resposta, rotulo):
            if numero not in validos and (rotulo, numero) not in problemas:
                problemas.append((rotulo, numero))
    return problemas
