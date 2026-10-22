"""Ponto de entrada: python -m src.data_acquisition.noticias [--fontes ...] [--listar] [--reprocessar]"""

import argparse

from src.data_acquisition.noticias.coletor import coletar_noticias
from src.data_acquisition.noticias.fontes import FONTES, NAO_INCLUIDAS


def listar() -> None:
    print("\nFontes configuradas:")
    for fonte in FONTES:
        situacao = "HABILITADA" if fonte.habilitada else "desabilitada"
        print(
            f"  {fonte.chave:14s} {situacao:13s} {fonte.nivel_texto:10s} {fonte.nome}"
        )
        if not fonte.habilitada:
            print(f"  {'':14s} motivo: {fonte.motivo}")
    print("\nAvaliadas e não incluídas:")
    for nome, motivo in NAO_INCLUIDAS.items():
        print(f"  {nome:14s} {motivo}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Coleta de notícias do SolarGap Brasil"
    )
    parser.add_argument(
        "--fontes", nargs="+", help="Chaves das fontes (padrão: todas as habilitadas)."
    )
    parser.add_argument(
        "--listar", action="store_true", help="Mostra a situação das fontes e sai."
    )
    parser.add_argument(
        "--reprocessar",
        action="store_true",
        help="Reextrai notícias já presentes no corpus (a partir do cache HTML).",
    )
    argumentos = parser.parse_args()

    if argumentos.listar:
        listar()
    else:
        coletar_noticias(chaves=argumentos.fontes, reprocessar=argumentos.reprocessar)
