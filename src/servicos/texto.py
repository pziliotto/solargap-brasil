"""
PROJETO: SolarGap Brasil
ARQUIVO: texto.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO: 13/11/2026 — TP4: texto_para_modelo não repete a linha fina quando
             ela é o próprio primeiro parágrafo do texto
             22/11/2026 — stopwords revisadas (negações, NLTK e spaCy) e filtro
             sem maiúsculas e acentos

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
import unicodedata
from collections import Counter
from collections.abc import Iterable
from functools import lru_cache

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

# Revisão de 22/11/2026: "não" era um dos termos mais frequentes da nuvem.
# Comparada com as listas em português do NLTK (207 palavras) e do spaCy (416),
# sem adicionar dependência: entram todas as do NLTK que faltavam e, do spaCy,
# só palavras funcionais, negações e numerais. Ficam de fora palavras da lista
# do spaCy que têm sentido neste domínio, como "sistema", "estado", "corrente",
# "valor", "conselho", "área", "nível", "potência" e "geral".
NEGACOES = set(
    """
    não nao nunca jamais nada nenhum nenhuma nenhuns nenhumas ninguém nem
    tampouco sequer
    """.split()
)
FUNCIONAIS_NLTK = set(
    """
    estamos estavam esteja estejam estejamos esteve estive estivemos estiver
    estivera estiveram estiverem estivermos estivesse estivessem estivéramos
    estivéssemos estou estávamos fomos for fora forem formos fosse fossem fui
    fôramos fôssemos haja hajam hajamos havemos haver hei houve houvemos houver
    houvera houveram houverei houverem houveremos houveria houveriam houvermos
    houverá houverão houveríamos houvesse houvessem houvéramos houvéssemos hão
    meus minhas nossa nossas nosso nossos seja sejam sejamos serei seremos
    seriam seríamos somos sou temos tenha tenham tenhamos tenho terei teremos
    teria teriam terá terão teríamos teu teus teve tive tivemos tiver tivera
    tiveram tiverem tivermos tivesse tivessem tivéramos tivéssemos tu tua tuas
    tínhamos vos éramos
    """.split()
)
FUNCIONAIS_SPACY = set(
    """
    acerca ademais agora algo algum alguma algumas alguns ali ambas ambos antes
    atrás bastante cá certamente contudo cuja cujas cujo cujos daquela daquelas
    daquele daqueles daquilo dar demais dentro diante disso disto diz dizem
    dizer dão embora fazem fazia faz faço fez inclusive ir irá logo menos
    muita muitas muitos naquela naquele nuns ora parece perante pode poder
    podia porquanto portanto posso pouca poucas pouco poucos quais qualquer
    quaisquer quer sempre sim sob somente tais tal talvez tudo vem vêm ver
    vária várias vários
    zero um dois duas três quatro cinco seis sete oito nove dez onze doze
    treze catorze quatorze quinze dezesseis dezessete dezoito dezenove vinte
    cem cento
    """.split()
)
STOPWORDS |= NEGACOES | FUNCIONAIS_NLTK | FUNCIONAIS_SPACY


def sem_acento(palavra: str) -> str:
    """Minúsculas e sem acentos: "Não" e "nao" viram a mesma chave."""
    return (
        unicodedata.normalize("NFKD", palavra.lower())
        .encode("ascii", "ignore")
        .decode()
    )


# Comparação sem maiúsculas e sem acentos: "nao" (sem til, comum em texto
# digitado) é filtrado como "não". A nuvem continua exibindo a grafia original.
STOPWORDS_NORMALIZADAS = frozenset(sem_acento(p) for p in STOPWORDS)
PADRAO_TOKEN = re.compile(r"[a-záàâãéêíóôõúüç]+")
TAMANHO_MINIMO_TOKEN = 3

# ~4 caracteres por token em português: 4.000 caracteres ≈ 1.000 tokens.
LIMITE_CARACTERES_MODELO = 4_000


@lru_cache(maxsize=50_000)
def _chave(token: str) -> str:
    return sem_acento(token)


def frequencia_termos(textos: Iterable[str]) -> dict[str, int]:
    """Conta os termos do corpus, sem stopwords, números e palavras curtas."""
    contagem: Counter = Counter()
    for texto in textos:
        for token in PADRAO_TOKEN.findall(str(texto).lower()):
            if (
                len(token) >= TAMANHO_MINIMO_TOKEN
                and _chave(token) not in STOPWORDS_NORMALIZADAS
            ):
                contagem[token] += 1
    return dict(contagem)


def _limpo(valor) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip()
    return "" if texto.lower() in {"nan", "none", "<na>"} else texto


def _espacos(valor: str) -> str:
    return " ".join(valor.split())


def _abre_o_texto(linha_fina: str, texto: str) -> bool:
    """Se a linha fina já aparece no início do texto (mesmo com espaços diferentes)."""
    if not linha_fina or not texto:
        return False
    inicio = _espacos(linha_fina)[:80]
    return inicio in _espacos(texto)[: len(linha_fina) + 200]


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
    titulo, linha_fina, texto = _limpo(titulo), _limpo(linha_fina), _limpo(texto)
    integral = nivel_texto == esquema.NIVEL_INTEGRAL

    # Em cerca de metade do corpus a "linha fina" coletada é o primeiro parágrafo
    # da matéria (o portal repete o lide na meta descrição). Repeti-la desperdiça
    # a janela de 512 tokens dos modelos locais com texto duplicado.
    if integral and _abre_o_texto(linha_fina, texto):
        linha_fina = ""

    partes = [titulo, linha_fina, texto if integral else ""]

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
