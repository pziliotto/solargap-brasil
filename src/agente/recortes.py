"""
PROJETO: SolarGap Brasil
ARQUIVO: agente/recortes.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026 (TP5)

DESCRIÇÃO:
    Encontra na pergunta a UF e o município de que o usuário está falando.

POR QUE NÃO DEIXAR ISSO PARA O LLM:
    Um modelo local pequeno erra o código IBGE com facilidade (inventa dígitos)
    e confunde homônimos: há 232 nomes de município repetidos no Brasil
    ("Bom Jesus" existe em cinco UFs). A busca é determinística, contra a
    própria Gold: o nome tem de existir, e o código vem da tabela, nunca do
    texto gerado. O LLM só decide QUAIS ferramentas usar.

REGRAS:
    - Comparação sem acento e sem diferença de maiúsculas, com prioridade para
      o trecho mais longo ("Rio Grande do Sul" vence "Rio Grande").
    - Nome de UF por extenso ou sigla em maiúsculas isolada ("RS", não "rs",
      para não confundir com palavras como "se" ou "to").
    - Município de uma palavra só casa se estiver com inicial maiúscula no
      texto original, para "palmas" (aplausos) não virar Palmas (TO).
    - Homônimo: vence o da UF citada na pergunta; sem UF, o de mais
      domicílios, e a ambiguidade é registrada para o agente avisar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

UFS = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia",
    "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe",
    "TO": "Tocantins",
}  # fmt: skip
# Apelidos comuns em perguntas de gestão.
APELIDOS_UF = {"gaucho": "RS", "gaucha": "RS", "paulista": "SP", "mineiro": "MG"}
CONECTIVOS = {"de", "da", "do", "das", "dos", "d'", "e"}
# Palavras de uma só que são município, mas aparecem em perguntas com outro
# sentido mesmo em maiúscula no início da frase.
PALAVRAS_COMUNS = {"onde", "qual", "quais", "como", "brasil", "sul", "norte"}
MAX_PALAVRAS = 7


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento, hífen e apóstrofo como espaço."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    sem_acento = re.sub(r"[-'’]", " ", sem_acento.lower())
    return re.sub(r"\s+", " ", sem_acento).strip()


@dataclass
class Recorte:
    uf: str | None = None
    cod_ibge: str | None = None
    nome_municipio: str | None = None
    ufs_citadas: list[str] = field(default_factory=list)
    homonimos: list[str] = field(default_factory=list)  # "Bom Jesus (PI)", ...

    @property
    def nivel(self) -> str:
        if self.cod_ibge:
            return "municipio"
        return "uf" if self.uf else "brasil"

    @property
    def descricao(self) -> str:
        if self.cod_ibge:
            return f"{self.nome_municipio} ({self.uf})"
        return UFS.get(self.uf, "Brasil") if self.uf else "Brasil"

    def como_dict(self) -> dict:
        return {
            "nivel": self.nivel,
            "uf": self.uf,
            "cod_ibge": self.cod_ibge,
            "municipio": self.nome_municipio,
            "descricao": self.descricao,
            "ufs_citadas": self.ufs_citadas,
            "homonimos": self.homonimos,
        }


_TOKEN = re.compile(r"[A-Za-zÀ-ÿ]+(?:['’-][A-Za-zÀ-ÿ]+)*|\S")


class Localizador:
    """Índice dos nomes de UF e município da Gold de potencial."""

    def __init__(self, municipal: pd.DataFrame):
        tabela = municipal[["cod_ibge", "nome", "uf", "domicilios"]].copy()
        tabela["chave"] = tabela["nome"].map(normalizar)
        self._municipios: dict[str, list[dict]] = {}
        for linha in tabela.sort_values("domicilios", ascending=False).itertuples():
            self._municipios.setdefault(linha.chave, []).append(
                {"cod_ibge": str(linha.cod_ibge), "nome": linha.nome, "uf": linha.uf}
            )
        self._ufs = {normalizar(nome): sigla for sigla, nome in UFS.items()}
        self._ufs.update(APELIDOS_UF)
        self._por_codigo = {
            str(r.cod_ibge): {"nome": r.nome, "uf": r.uf} for r in tabela.itertuples()
        }

    # ─────────── consultas diretas ───────────

    def municipio_por_codigo(self, cod_ibge: str) -> dict | None:
        return self._por_codigo.get(str(cod_ibge))

    def municipio_por_nome(self, nome: str, uf: str | None = None) -> dict | None:
        candidatos = self._municipios.get(normalizar(nome), [])
        if uf:
            candidatos = [c for c in candidatos if c["uf"] == uf.upper()] or []
        return candidatos[0] if candidatos else None

    # ─────────── varredura da pergunta ───────────

    def _candidatos(self, tokens: list[str]) -> list[tuple[int, int, str, object]]:
        """Todos os trechos que são UF ou município: (início, tamanho, tipo, valor)."""
        normalizados = [normalizar(t) for t in tokens]
        candidatos = []
        for i, token in enumerate(tokens):
            if len(token) == 2 and token.isupper() and token in UFS:
                candidatos.append((i, 1, "uf", token))
            if normalizados[i] in APELIDOS_UF:
                candidatos.append((i, 1, "uf", APELIDOS_UF[normalizados[i]]))
        for tamanho in range(1, MAX_PALAVRAS + 1):
            for i in range(len(tokens) - tamanho + 1):
                janela = tokens[i : i + tamanho]
                if not janela[0][:1].isupper():
                    continue
                if not all(
                    t[:1].isupper() or normalizar(t) in CONECTIVOS for t in janela
                ):
                    continue
                chave = " ".join(normalizados[i : i + tamanho])
                if chave in self._ufs:
                    candidatos.append((i, tamanho, "uf", self._ufs[chave]))
                elif chave in self._municipios and not (
                    tamanho == 1 and chave in PALAVRAS_COMUNS
                ):
                    candidatos.append(
                        (i, tamanho, "municipio", self._municipios[chave])
                    )
        return candidatos

    def localizar(self, pergunta: str) -> Recorte:
        """Escolhe os trechos mais longos sem sobreposição. Empate: a UF vence
        ("São Paulo" e "Rio de Janeiro" são lidos como estado)."""
        tokens = _TOKEN.findall(pergunta)
        candidatos = sorted(
            self._candidatos(tokens), key=lambda c: (-c[1], c[2] != "uf", c[0])
        )
        ocupadas: set[int] = set()
        escolhidos = []
        for inicio, tamanho, tipo, valor in candidatos:
            faixa = set(range(inicio, inicio + tamanho))
            if ocupadas & faixa:
                continue
            ocupadas |= faixa
            escolhidos.append((inicio, tipo, valor))
        escolhidos.sort(key=lambda e: e[0])
        ufs = list(dict.fromkeys(v for _, t, v in escolhidos if t == "uf"))
        municipios = [v for _, t, v in escolhidos if t == "municipio"]

        recorte = Recorte(ufs_citadas=ufs, uf=ufs[0] if ufs else None)
        if not municipios:
            return recorte
        candidatos_mun = municipios[0]
        escolhido = next(
            (c for c in candidatos_mun if c["uf"] in ufs), candidatos_mun[0]
        )
        if len(candidatos_mun) > 1 and not any(c["uf"] in ufs for c in candidatos_mun):
            recorte.homonimos = [f"{c['nome']} ({c['uf']})" for c in candidatos_mun]
        recorte.uf = escolhido["uf"]
        recorte.cod_ibge = escolhido["cod_ibge"]
        recorte.nome_municipio = escolhido["nome"]
        return recorte
