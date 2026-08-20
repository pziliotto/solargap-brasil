"""
PROJETO: SolarGap Brasil
ARQUIVO: ibge.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 17/08/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Coleta a população residente do Censo Demográfico 2022 via API de dados
    Agregados do IBGE - unificado para os níveis UF e Município através de
    uma única função parametrizada.

TABELA SIDRA: 9923 - "População residente, por situação de domicílio"
VARIÁVEL: 93 - "População residente" (Pessoas)
CLASSIFICAÇÃO: 1 -> CATEGORIA: 6795 -> "All"

view=flat:
    a API devolve os dadados já achatados em uma lista de registros,
    em vez de uma estrutura aninhada variável -> resultados -> séries usadas nos
    scripts anteriores.

OBS.:
    Verificar as chaves abreviadas específicas do IBGE antes de escrever códigos
    da camada de tratamento.

OBS.:
    São recebidos 28 valores ao invés de 27, por conta da legenda que acompanha o
    view=flat
"""

from __future__ import annotations

import logging

from src.data_acquisition.coletor_base import (
    configurar_logging,
    obter_project_root,
    requisitar,
    salvar_raw_json,
)

PROJECT_ROOT = obter_project_root(__file__)
PASTA_RAW = PROJECT_ROOT / "data" / "raw"
PASTA_LOGS = PROJECT_ROOT / "logs"

URL_BASE = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/9923/periodos/2022/variaveis/93"
)

NIVEIS = {
    "uf": {
        "codigo_localidade": "N3[all]",
        "nome_arquivo": "demografico_uf_2022.json",
        "total_esperado": 27,
    },
    "municipio": {
        "codigo_localidade": "N6[all]",
        "nome_arquivo": "demografico_municipio_2022.json",
        "total_esperado": 5570,
    },
}


def montar_url(nivel: str) -> str:
    config = NIVEIS[nivel]
    return f"{URL_BASE}?localidades={config['codigo_localidade']}&classificacao=1[6795]&view=flat"


def coletar_ibge(nivel: str) -> None:
    """Coleta e salva a população residente para o nível territorial dado.

    nivel: "uf" ou "municipio" — chave do dicionário NIVEIS.
    """
    if nivel not in NIVEIS:
        raise ValueError(f"Nível '{nivel}' desconhecido. Use um de: {list(NIVEIS)}")

    config = NIVEIS[nivel]
    caminho_log = configurar_logging(f"IBGE_{nivel.upper()}", PASTA_LOGS)
    logging.info("=" * 70)
    logging.info("Coleta IBGE — nível: %s", nivel)
    logging.info("Raiz do projeto: %s", PROJECT_ROOT)

    url = montar_url(nivel)
    timeout = 120 if nivel == "municipio" else 30  # payload municipal é bem maior

    try:
        resposta = requisitar(url, timeout=timeout)
    except Exception:
        logging.error("Coleta abortada. Nenhum arquivo foi gravado.")
        raise

    dados = resposta.json()  # em view=flat, já é uma lista achatada de registros
    quantidade = len(dados)
    logging.info("Registros retornados: %d", quantidade)

    if quantidade != config["total_esperado"]:
        logging.warning(
            "Esperava %d registros, recebi %d. Verifique os parâmetros da consulta.",
            config["total_esperado"],
            quantidade,
        )

    caminho_arquivo = PASTA_RAW / config["nome_arquivo"]
    salvar_raw_json(dados, caminho_arquivo)

    tamanho_kb = caminho_arquivo.stat().st_size / 1024
    logging.info("Arquivo salvo: %s (%.1f KB)", caminho_arquivo, tamanho_kb)
    logging.info("Log da sessão: %s", caminho_log)
    logging.info("Coleta concluída com sucesso.")
    logging.info("=" * 70)


if __name__ == "__main__":
    coletar_ibge("uf")
    coletar_ibge("municipio")
