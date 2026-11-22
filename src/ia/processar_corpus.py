"""
PROJETO: SolarGap Brasil
ARQUIVO: processar_corpus.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 16/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Processamento em lote do corpus de notícias com os modelos locais:
        resumo      PTT5 (recogna-nlp/ptt5-base-summ)
        relevância  híbrida: termo de GD no título OU mDeBERTa zero-shot
                    ("Esta notícia trata de energia solar.", limiar 0,4)

    O resultado vai para data/processed/corpus_ia.csv (camada Gold), ligado
    ao corpus pelo id, e é versionado no Git. Assim o dashboard e a API mostram
    resumo e relevância em qualquer máquina, sem GPU e sem baixar os modelos.

FONTES SEM DERIVAÇÃO (22/11/2026):
    ANEEL, MME e Agência Gov publicam sob licença que proíbe obra derivada
    (CC BY-ND, gov.br). Para elas só a relevância é calculada; o resumo fica
    vazio (esquema.FONTES_SEM_DERIVACAO).

POR QUE O TOM NÃO É PROCESSADO:
    No benchmark, o tom zero-shot ficou abaixo da linha de base de classe
    majoritária (docs/escolha_modelo.md). Gravar um rótulo que erra mais que
    um chute constante daria aparência de dado a algo que não é. O tom segue
    disponível na API, marcado como experimental.

INCREMENTAL:
    Notícias já processadas pelo MESMO par de modelos são puladas. Trocar de
    modelo (catálogo ou variável de ambiente) ou usar --refazer reprocessa.

ENTRADA DO MODELO:
    texto_para_modelo (src/servicos/texto.py): título + linha fina + texto,
    conforme o nível de texto da fonte. É a mesma entrada da rota
    POST /noticias/{id}/processar, então lote e API dão o mesmo resultado.

OBS. DE USO (a partir da raiz):
    python -m src.ia.processar_corpus              # só as pendentes
    python -m src.ia.processar_corpus --refazer    # todas
    python -m src.ia.processar_corpus --limite 5   # teste rápido
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.data_acquisition.coletor_base import configurar_logging, obter_project_root
from src.ia import catalogo
from src.ia.catalogo import Tarefa
from src.ia.motor import GerenciadorModelos
from src.preparacao import esquema
from src.servicos import dados
from src.servicos.texto import texto_para_modelo

PROJECT_ROOT = obter_project_root(__file__)
PASTA_LOGS = PROJECT_ROOT / "logs"
SEPARADOR = ";"

logger = logging.getLogger(__name__)


def modelo_relevancia(gerenciador: GerenciadorModelos) -> str:
    """Modelo + estratégia: trocar qualquer um dos dois torna a notícia pendente."""
    hf_id = gerenciador.configs[Tarefa.relevancia].hf_id
    return f"{hf_id} | {catalogo.ESTRATEGIA_RELEVANCIA}"


def pendentes(
    corpus: pd.DataFrame,
    existente: pd.DataFrame | None,
    modelos: dict[str, str],
    refazer: bool,
) -> pd.DataFrame:
    """Notícias sem resultado do par de modelos atual."""
    if refazer or existente is None or existente.empty:
        return corpus
    atual = existente[
        (existente["modelo_resumo"] == modelos["resumo"])
        & (existente["modelo_relevancia"] == modelos["relevancia"])
    ]
    return corpus[~corpus["id"].isin(atual["id"])]


def processar(
    corpus: pd.DataFrame, gerenciador: GerenciadorModelos, limite: int | None = None
) -> pd.DataFrame:
    """Executa resumo e relevância em cada notícia; devolve no formato de corpus_ia."""
    modelos = {
        "resumo": gerenciador.configs[Tarefa.resumo].hf_id,
        "relevancia": modelo_relevancia(gerenciador),
    }
    alvo = corpus.head(limite) if limite else corpus
    linhas = []
    for i, noticia in enumerate(alvo.itertuples(index=False), start=1):
        entrada = texto_para_modelo(
            noticia.titulo, noticia.linha_fina, noticia.texto, noticia.nivel_texto
        )
        # Licença sem derivação (CC BY-ND): o resumo nem é gerado nem guardado.
        resumo = (
            gerenciador.resumir(entrada)
            if esquema.permite_resumo(noticia.fonte)
            else None
        )
        relevancia = gerenciador.avaliar_relevancia(entrada, noticia.titulo)
        linhas.append(
            {
                "id": noticia.id,
                "resumo": resumo.resumo if resumo else None,
                "resumo_truncado": resumo.truncado if resumo else None,
                "relevante": relevancia.relevante,
                "relevancia_prob": relevancia.probabilidade,
                "relevancia_por_termo": relevancia.por_termo_gd,
                "modelo_resumo": modelos["resumo"],
                "modelo_relevancia": modelos["relevancia"],
                "processado_em": datetime.now().replace(microsecond=0).isoformat(),
            }
        )
        if i % 10 == 0 or i == len(alvo):
            logger.info("  %d/%d notícias processadas", i, len(alvo))
    return pd.DataFrame(linhas, columns=esquema.COLUNAS_CORPUS_IA)


def mesclar(existente: pd.DataFrame | None, novo: pd.DataFrame) -> pd.DataFrame:
    """Novo resultado substitui o antigo da mesma notícia; os demais ficam."""
    if existente is None or existente.empty:
        return novo
    if novo.empty:
        return existente
    restante = existente[~existente["id"].isin(novo["id"])]
    return pd.concat([restante, novo], ignore_index=True)


def executar(
    pasta: Path = dados.PASTA_PROCESSED,
    refazer: bool = False,
    limite: int | None = None,
    gerenciador: GerenciadorModelos | None = None,
) -> pd.DataFrame:
    corpus = dados.carregar_corpus(pasta)
    existente = dados.carregar_corpus_ia(pasta)
    gerenciador = gerenciador or GerenciadorModelos()
    modelos = {
        "resumo": gerenciador.configs[Tarefa.resumo].hf_id,
        "relevancia": modelo_relevancia(gerenciador),
    }

    alvo = pendentes(corpus, existente, modelos, refazer)
    logger.info("Corpus: %d notícias | a processar: %d", len(corpus), len(alvo))
    if alvo.empty:
        logger.info("Nada a fazer: todas as notícias já foram processadas.")
        return existente

    gerenciador.carregar()
    if not gerenciador.todas_prontas():
        falhas = {
            t.value: gerenciador.situacao(t).erro
            for t in (Tarefa.resumo, Tarefa.relevancia)
        }
        raise RuntimeError(f"Modelos não carregaram: {falhas}")

    resultado = mesclar(existente, processar(alvo, gerenciador, limite))
    destino = pasta / esquema.ARQUIVO_CORPUS_IA
    resultado.sort_values("id").to_csv(
        destino, sep=SEPARADOR, index=False, encoding="utf-8"
    )

    relevantes = resultado["relevante"].astype(str).str.lower().eq("true").sum()
    logger.info("Gravado: %s (%d notícias)", destino, len(resultado))
    logger.info(
        "Julgadas relevantes: %d (%.0f%%)",
        relevantes,
        100 * relevantes / len(resultado),
    )
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resumo e relevância do corpus com modelos locais."
    )
    parser.add_argument(
        "--refazer", action="store_true", help="reprocessa todas as notícias"
    )
    parser.add_argument(
        "--limite", type=int, help="processa só as N primeiras pendentes"
    )
    args = parser.parse_args()

    caminho_log = configurar_logging("PROCESSAR_CORPUS_IA", PASTA_LOGS)
    executar(refazer=args.refazer, limite=args.limite)
    logger.info("Log da sessão: %s", caminho_log)


if __name__ == "__main__":
    main()
