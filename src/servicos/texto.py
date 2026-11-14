"""
PROJETO: SolarGap Brasil
ARQUIVO: texto.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Processamento de texto do corpus de notícias, sem dependência de interface:
        - frequencia_termos: contagem de termos para a nuvem de palavras e o
          gráfico de termos (movida de src/app/carregamento.py, TP2);
        - texto_para_modelo: o texto exato que o modelo de linguagem receberá
          no TP4, montado conforme o nível de texto de cada notícia.

PREPARAÇÃO PARA O TP4 (LLM):
    O corpus mistura dois níveis de texto (esquema.NIVEIS_TEXTO):
        integral  -> há texto completo: o modelo recebe título + linha fina + texto
        metadados -> só título e linha fina: o modelo recebe apenas esses campos
    Centralizar essa montagem aqui garante que a API (GET /noticias/{id}), o
    painel e, no TP4, a rota POST /processar_texto usem a MESMA entrada para o
    modelo. O limite de caracteres protege a janela de contexto de modelos
    locais pequenos (ex.: BERTimbau, 512 tokens; mT5-small, 1.024 tokens).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from src.preparacao import esquema

# Palavras sem valor informativo para a nuvem: artigos, preposições,
# pronomes, verbos auxiliares e jargão de texto jornalístico.
STOPWORDS = set(
    [
        "a",
        "ao",
        "aos",
        "aquela",
        "aquelas",
        "aquele",
        "aqueles",
        "aquilo",
        "as",
        "até",
        "com",
        "como",
        "da",
        "das",
        "de",
        "dela",
        "delas",
        "dele",
        "deles",
        "depois",
        "do",
        "dos",
        "e",
        "ela",
        "elas",
        "ele",
        "eles",
        "em",
        "entre",
        "era",
        "eram",
        "essa",
        "essas",
        "esse",
        "esses",
        "esta",
        "estas",
        "este",
        "estes",
        "eu",
        "foi",
        "foram",
        "há",
        "isso",
        "isto",
        "já",
        "lhe",
        "lhes",
        "mais",
        "mas",
        "me",
        "mesmo",
        "meu",
        "minha",
        "muito",
        "na",
        "nas",
        "nem",
        "no",
        "nos",
        "nós",
        "num",
        "numa",
        "o",
        "os",
        "ou",
        "para",
        "pela",
        "pelas",
        "pelo",
        "pelos",
        "por",
        "qual",
        "quando",
        "que",
        "quem",
        "se",
        "sem",
        "ser",
        "seu",
        "seus",
        "só",
        "sua",
        "suas",
        "também",
        "te",
        "tem",
        "têm",
        "ter",
        "um",
        "uma",
        "umas",
        "uns",
        "você",
        "vocês",
        "à",
        "às",
        "é",
        "são",
        "está",
        "estão",
        "estava",
        "será",
        "serão",
        "seria",
        "pode",
        "podem",
        "poderá",
        "deve",
        "devem",
        "vai",
        "vão",
        "sobre",
        "após",
        "ainda",
        "segundo",
        "disse",
        "afirmou",
        "explicou",
        "destacou",
        "informou",
        "acordo",
        "ano",
        "anos",
        "mil",
        "milhão",
        "milhões",
        "bilhão",
        "bilhões",
        "cerca",
        "além",
        "outros",
        "outras",
        "outro",
        "outra",
        "cada",
        "todo",
        "toda",
        "todos",
        "todas",
        "onde",
        "assim",
        "então",
        "porque",
        "porém",
        "bem",
        "apenas",
        "agência",
        "brasil",
        "hoje",
        "dia",
        "dias",
        "mês",
        "meses",
        "parte",
        "forma",
        "desde",
        "contra",
        "durante",
        "sendo",
        "tendo",
        "feito",
        "fazer",
        "faz",
        "vez",
        "vezes",
        "grande",
        "grandes",
        "novo",
        "nova",
        "novos",
        "novas",
        "primeiro",
        "primeira",
        "maior",
        "maiores",
        "menor",
        "menores",
        "ser",
        "sido",
        "estar",
        "tinha",
        "tinham",
        "caso",
        "casos",
        "sobre",
        "total",
        "através",
        "conforme",
        "enquanto",
        "dessa",
        "desse",
        "desta",
        "deste",
        "nessa",
        "nesse",
        "nesta",
        "neste",
        "pois",
        "lá",
        "aqui",
        "aí",
        "tanto",
        "tanta",
        "tão",
        "quanto",
        "quanta",
    ]
)
PADRAO_TOKEN = re.compile(r"[a-záàâãéêíóôõúüç]+")
TAMANHO_MINIMO_TOKEN = 3

# ~4 caracteres por token em português: 4.000 caracteres ≈ 1.000 tokens.
LIMITE_CARACTERES_MODELO = 4_000


def frequencia_termos(textos: Iterable[str]) -> dict[str, int]:
    """Conta os termos do corpus, sem stopwords, números e palavras curtas."""
    contagem: Counter = Counter()
    for texto in textos:
        for token in PADRAO_TOKEN.findall(str(texto).lower()):
            if len(token) >= TAMANHO_MINIMO_TOKEN and token not in STOPWORDS:
                contagem[token] += 1
    return dict(contagem)


def _limpo(valor) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip()
    return "" if texto.lower() in {"nan", "none", "<na>"} else texto


def texto_para_modelo(
    titulo: str,
    linha_fina: str | None,
    texto: str | None,
    nivel_texto: str | None,
    limite: int = LIMITE_CARACTERES_MODELO,
) -> str:
    """Monta a entrada do modelo de linguagem para uma notícia.

    Notícias de nível "metadados" nunca usam o campo texto, mesmo que ele venha
    preenchido por engano: o nível é o que a licença da fonte permite usar.
    """
    partes = [_limpo(titulo), _limpo(linha_fina)]
    if nivel_texto == esquema.NIVEL_INTEGRAL:
        partes.append(_limpo(texto))

    entrada = "\n\n".join(p for p in partes if p)
    if len(entrada) <= limite:
        return entrada

    # Corta no último espaço antes do limite, para não partir palavras.
    corte = entrada.rfind(" ", 0, limite)
    return entrada[: corte if corte > 0 else limite].rstrip() + " [...]"


def detectar_ufs(texto: str) -> str:
    """Siglas das UFs cujo nome aparece no texto, separadas por vírgula.

    Movida do noticias.py (TP2) para cá: agora o scraper e a API (POST /noticias)
    detectam as UFs com a mesma regra. Fronteira de palavra evita falsos
    positivos, e "Mato Grosso" não casa com "Mato Grosso do Sul".
    """
    encontradas = []
    for sigla, (_, nome) in esquema.UFS.items():
        padrao = rf"\b{re.escape(nome)}\b"
        if nome == "Mato Grosso":
            padrao += r"(?! do Sul)"
        if re.search(padrao, texto or ""):
            encontradas.append(sigla)
    return ",".join(encontradas)
