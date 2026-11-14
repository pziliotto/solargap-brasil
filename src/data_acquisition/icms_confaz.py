"""
PROJETO: SolarGap Brasil
ARQUIVO: icms_confaz.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Coleta a adesão das 27 UFs ao Convênio ICMS 16/15 (CONFAZ), que autoriza a
    isenção de ICMS sobre a energia compensada na geração distribuída, e gera
    uma tabela de dimensão de política pública por UF.

FONTE E ESTRATÉGIA:
    1. Página oficial do CONFAZ (CV016_15), via BeautifulSoup — SOMENTE se o
       robots.txt permitir o acesso automatizado com o User-Agent do projeto.
       O HTML baixado vai para o cache da camada Bronze (data/raw/html/confaz/).
    2. Caso contrário (proibido ou ilegível), a cópia de referência do texto
       oficial em data/external/confaz/convenio_icms_16_15.txt. Atos oficiais
       não têm proteção autoral (Lei 9.610/98, art. 8º, IV).
    A origem efetiva fica registrada em cada linha (coluna origem_texto).
    Na avaliação do TP3, o robots.txt do CONFAZ bloqueou o acesso automatizado.

O QUE O PARSER EXTRAI DO TEXTO LEGAL:
    - UFs da redação original da cláusula primeira (GO, PE, SP) — data de
      adesão = ratificação nacional do convênio;
    - notas "Adesão de XX e YY, a partir de DD.MM.AA, pelo Conv. ICMS NN/AA";
    - UFs que só aparecem numa nova redação da cláusula primeira, sem nota de
      adesão própria (PB, PI, RO e SE, pelo Conv. ICMS 75/16) — inclusão
      INFERIDA da redação, sinalizada na coluna observacao;
    - limites de prazo do § 3º (48 meses para PR e, até o Conv. 114/23, SC).

INÍCIO DOS EFEITOS:
    A cláusula terceira fixa efeitos a partir de 01/09/2015. Adesões anteriores
    (GO, PE, SP, RN, CE, TO) só produzem efeito a partir dessa data:
    inicio_efeitos = max(data_adesao, 01/09/2015).

SAÍDA (camada Gold — dimensão pequena, 27 linhas, sem etapa Silver):
    data/processed/gold_icms_uf.csv

OBS. DE USO:
    python -m src.data_acquisition.icms_confaz
"""

from __future__ import annotations

import logging
import re
import sys
from datetime import date, datetime

import pandas as pd
from bs4 import BeautifulSoup

from src.data_acquisition.coletor_base import configurar_logging, obter_project_root
from src.data_acquisition.noticias.base import Navegador
from src.preparacao import esquema
from src.servicos.texto import detectar_ufs

PROJECT_ROOT = obter_project_root(__file__)
URL_CONFAZ = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2015/CV016_15"
CACHE_HTML = PROJECT_ROOT / "data" / "raw" / "html" / "confaz" / "CV016_15.html"
REFERENCIA_LOCAL = (
    PROJECT_ROOT / "data" / "external" / "confaz" / "convenio_icms_16_15.txt"
)
SAIDA = PROJECT_ROOT / "data" / "processed" / "gold_icms_uf.csv"
PASTA_LOGS = PROJECT_ROOT / "logs"

CONVENIO_BASE = "16/15"
DATA_REFERENCIA = date(esquema.ANO_PARCIAL, 8, 31)  # referência da base ANEEL (08/2026)
MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

PADRAO_RATIFICACAO = re.compile(r"Ratificação nacional no DOU de (\d{2}\.\d{2}\.\d{2})")
PADRAO_INICIO_EFEITOS = re.compile(
    r"produzindo efeitos para os fatos geradores ocorridos a partir de (\d{1,2})º? de ([a-zç]+) de (\d{4})"
)
PADRAO_ADESAO = re.compile(
    r"Adesão d[aeo]s?\s+(?P<ufs>[A-Z]{2}(?:(?:,\s*|\s+e\s+)[A-Z]{2})*),\s*"
    r"a partir de\s+(?P<data>\d{2}\.\d{2}\.\d{2}),\s*pelo Conv\.\s*ICMS\s+(?P<conv>\d+/\d{2})"
)
PADRAO_VERSAO_CAPUT = re.compile(
    r"(?P<nota>Redação original|(?:Nova redação|Redação anterior) dada ao caput da cláusula primeira "
    r"pelo Conv\.\s*ICMS\s+(?P<conv>\d+/\d{2})),\s*(?P<efeitos>.*?)\s*"
    r"Cláusula [Pp]rimeira\s+Ficam os Estados\s+(?P<estados>.+?)\s+autorizados",
    re.DOTALL,
)
PADRAO_PARAGRAFO_3 = re.compile(
    r"(?:Acrescido § ?3º à cláusula primeira|Nova redação dada ao § ?3º da cláusula primeira) "
    r"pelo Conv\.\s*ICMS\s+(?P<conv>\d+/\d{2}).*?§\s*3º\s*Para o(?:s)? Estado(?:s)?\s+(?P<estados>.+?),"
    r"\s*o benefício previsto no caput será concedido pelo prazo máximo de (?P<meses>\d+)",
    re.DOTALL,
)


# ═══════════════════ Obtenção do texto ═══════════════════


def obter_texto() -> tuple[str, str]:
    """Devolve (texto, origem). Online só com robots.txt permitindo."""
    navegador = Navegador()
    situacao = navegador.diagnosticar(URL_CONFAZ)
    logging.info("robots.txt do CONFAZ para %s: %s", URL_CONFAZ, situacao)

    if situacao == "permitido":
        html = navegador.baixar(URL_CONFAZ)
        if html:
            CACHE_HTML.parent.mkdir(parents=True, exist_ok=True)
            CACHE_HTML.write_text(html, encoding="utf-8")
            texto = BeautifulSoup(html, "html.parser").get_text("\n")
            return texto, "confaz_online"
        logging.warning("Download do CONFAZ falhou; usando a cópia de referência.")
    else:
        logging.warning(
            "Acesso automatizado ao CONFAZ %s pelo robots.txt; usando a cópia de referência.",
            "não permitido" if situacao == "proibido" else "não verificável",
        )

    if not REFERENCIA_LOCAL.exists():
        logging.error("Cópia de referência não encontrada: %s", REFERENCIA_LOCAL)
        sys.exit(1)
    linhas = REFERENCIA_LOCAL.read_text(encoding="utf-8").splitlines()
    return "\n".join(
        linha for linha in linhas if not linha.lstrip().startswith("#")
    ), "referencia_local"


# ═══════════════════ Parser do texto legal ═══════════════════


def _data(texto_ddmmaa: str) -> date:
    return datetime.strptime(texto_ddmmaa, "%d.%m.%y").date()


def _ordem_convenio(convenio: str) -> tuple[int, int]:
    """'42/18' -> (2018, 42): ordem cronológica dos convênios."""
    numero, ano = convenio.split("/")
    return 2000 + int(ano), int(numero)


def _siglas(trecho: str) -> list[str]:
    """Siglas ("BA, MA e DF") ou nomes ("Estados do Acre, ... e o Distrito Federal")."""
    siglas = [s for s in re.findall(r"\b[A-Z]{2}\b", trecho) if s in esquema.UFS]
    return siglas or [s for s in detectar_ufs(trecho).split(",") if s]


def interpretar_convenio(texto: str) -> pd.DataFrame:
    texto = re.sub(r"\s+", " ", texto)

    ratificacao = PADRAO_RATIFICACAO.search(texto)
    inicio = PADRAO_INICIO_EFEITOS.search(texto)
    if not ratificacao or not inicio:
        raise ValueError(
            "Texto do convênio sem data de ratificação ou de início dos efeitos."
        )
    data_ratificacao = _data(ratificacao[1])
    inicio_convenio = date(int(inicio[3]), MESES[inicio[2].lower()], int(inicio[1]))

    adesoes: dict[str, dict] = {}

    def registrar(sigla, convenio, data_adesao, forma, observacao=None):
        if sigla not in adesoes:  # a primeira inclusão encontrada prevalece
            adesoes[sigla] = {
                "sigla_uf": sigla,
                "convenio_adesao": convenio,
                "data_adesao": data_adesao,
                "forma_inclusao": forma,
                "observacao": observacao,
            }

    versoes = []
    for versao in PADRAO_VERSAO_CAPUT.finditer(texto):
        efeitos = versao["efeitos"]
        inicio_versao = re.search(
            r"(?:a partir de|efeitos de)\s+(\d{2}\.\d{2}\.\d{2})", efeitos
        )
        versoes.append(
            {
                "convenio": versao["conv"] or CONVENIO_BASE,
                "original": versao["nota"] == "Redação original",
                "vigente": versao["nota"].startswith("Nova redação"),
                "sem_efeitos": "sem efeitos" in efeitos,
                "inicio": _data(inicio_versao[1]) if inicio_versao else inicio_convenio,
                "ufs": _siglas(versao["estados"]),
            }
        )
    if not versoes:
        raise ValueError("Nenhuma redação da cláusula primeira encontrada no texto.")

    # 1. Redação original: UFs signatárias desde a ratificação
    for versao in (v for v in versoes if v["original"]):
        for sigla in versao["ufs"]:
            registrar(sigla, CONVENIO_BASE, data_ratificacao, "texto original")

    # 2. Notas de adesão
    for nota in PADRAO_ADESAO.finditer(texto):
        for sigla in _siglas(nota["ufs"]):
            registrar(sigla, nota["conv"], _data(nota["data"]), "convênio de adesão")

    # 3. UFs só presentes em nova redação da cláusula (sem nota própria): inferência
    for versao in sorted(
        (v for v in versoes if not v["sem_efeitos"]), key=lambda v: v["inicio"]
    ):
        for sigla in versao["ufs"]:
            registrar(
                sigla,
                versao["convenio"],
                versao["inicio"],
                "nova redação da cláusula primeira",
                f"Inclusão inferida da redação dada pelo Conv. ICMS {versao['convenio']}: "
                "o texto consolidado não traz nota de adesão própria.",
            )

    vigente = next((v for v in versoes if v["vigente"]), None)
    if vigente and set(vigente["ufs"]) != set(esquema.UFS):
        faltam = sorted(set(esquema.UFS) - set(vigente["ufs"]))
        logging.warning("Redação vigente não lista todas as UFs. Ausentes: %s", faltam)

    # § 3º: limite de prazo. Vale a versão mais recente; quem saiu dela perdeu o limite.
    paragrafos = sorted(
        PADRAO_PARAGRAFO_3.finditer(texto), key=lambda m: _ordem_convenio(m["conv"])
    )
    if paragrafos:
        atual = paragrafos[-1]
        com_limite = set(_siglas(atual["estados"]))
        for sigla in com_limite:
            if sigla in adesoes:
                adesoes[sigla]["observacao"] = (
                    f"Benefício limitado a {atual['meses']} meses, na forma da legislação estadual "
                    f"(§ 3º, redação do Conv. ICMS {atual['conv']})."
                )
        for anterior in paragrafos[:-1]:
            for sigla in set(_siglas(anterior["estados"])) - com_limite:
                if sigla in adesoes:
                    adesoes[sigla]["observacao"] = (
                        f"Limite de {anterior['meses']} meses (Conv. ICMS {anterior['conv']}) "
                        f"retirado pelo Conv. ICMS {atual['conv']}."
                    )

    tabela = pd.DataFrame(list(adesoes.values()))
    tabela["inicio_efeitos"] = tabela["data_adesao"].map(
        lambda d: max(d, inicio_convenio)
    )
    return tabela


def montar_tabela(adesoes: pd.DataFrame, origem: str) -> pd.DataFrame:
    tabela = adesoes.copy()
    tabela["nome_uf"] = tabela["sigla_uf"].map(lambda s: esquema.UFS[s][1])
    tabela["regiao"] = tabela["sigla_uf"].map(esquema.REGIAO_POR_UF)
    tabela["ano_inicio_efeitos"] = tabela["inicio_efeitos"].map(lambda d: d.year)
    tabela["meses_desde_inicio"] = tabela["inicio_efeitos"].map(
        lambda d: (DATA_REFERENCIA.year - d.year) * 12 + DATA_REFERENCIA.month - d.month
    )
    tabela["origem_texto"] = origem
    colunas = [
        "sigla_uf",
        "nome_uf",
        "regiao",
        "convenio_adesao",
        "data_adesao",
        "inicio_efeitos",
        "ano_inicio_efeitos",
        "meses_desde_inicio",
        "forma_inclusao",
        "observacao",
        "origem_texto",
    ]
    return (
        tabela[colunas]
        .sort_values(["inicio_efeitos", "sigla_uf"])
        .reset_index(drop=True)
    )


def validar(tabela: pd.DataFrame) -> None:
    faltantes = sorted(set(esquema.UFS) - set(tabela["sigla_uf"]))
    if faltantes:
        raise ValueError(f"UFs sem adesão identificada: {faltantes}")
    if tabela["sigla_uf"].duplicated().any():
        raise ValueError("UF repetida na tabela de adesão.")
    if len(tabela) != esquema.TOTAL_UFS:
        raise ValueError(
            f"Tabela com {len(tabela)} linhas; esperado {esquema.TOTAL_UFS}."
        )


# ═══════════════════ Execução ═══════════════════


def coletar_icms() -> pd.DataFrame:
    caminho_log = configurar_logging("ICMS_CONFAZ", PASTA_LOGS)
    logging.info("=" * 70)
    logging.info("Adesão ao Convênio ICMS 16/15 — CONFAZ")

    texto, origem = obter_texto()
    tabela = montar_tabela(interpretar_convenio(texto), origem)
    validar(tabela)

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(SAIDA, index=False, sep=";", encoding="utf-8")

    logging.info("Origem do texto: %s", origem)
    for ano, grupo in tabela.groupby("ano_inicio_efeitos"):
        logging.info("  %d: %s", ano, ", ".join(grupo["sigla_uf"]))
    inferidas = tabela[tabela["forma_inclusao"] == "nova redação da cláusula primeira"]
    if not inferidas.empty:
        logging.info(
            "Inclusões inferidas da redação: %s", ", ".join(inferidas["sigla_uf"])
        )
    logging.info("Salvo: %s (%d UFs)", SAIDA, len(tabela))
    logging.info("Log da sessão: %s", caminho_log)
    logging.info("=" * 70)
    return tabela


if __name__ == "__main__":
    coletar_icms()
