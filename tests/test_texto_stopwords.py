"""Nuvem de palavras: stopwords revisadas e filtro sem maiúsculas e acentos."""

from __future__ import annotations

import pytest

from src.servicos.texto import STOPWORDS, frequencia_termos, sem_acento


@pytest.mark.parametrize(
    "palavra",
    [
        "não",
        "Não",
        "NÃO",
        "nao",
        "Nao",
        "nunca",
        "nenhuma",
        "ninguém",
        "ninguem",
        "jamais",
    ],
)
def test_negacoes_filtradas_com_e_sem_acento(palavra):
    assert frequencia_termos([f"{palavra} {palavra} usina"]) == {"usina": 1}


@pytest.mark.parametrize(
    "palavra",
    ["estavam", "houve", "tenho", "seriam", "nossos", "três", "tres", "dois", "talvez"],
)
def test_funcionais_do_nltk_e_do_spacy(palavra):
    assert palavra not in frequencia_termos([f"{palavra} geração"])


@pytest.mark.parametrize(
    "palavra",
    ["sistema", "estado", "corrente", "valor", "conselho", "potência", "geral"],
)
def test_palavras_do_dominio_ficam(palavra):
    """Estão na lista do spaCy, mas têm sentido no setor elétrico."""
    assert sem_acento(palavra) not in {sem_acento(p) for p in STOPWORDS}
    assert frequencia_termos([palavra]) == {palavra: 1}


def test_grafia_original_preservada_na_contagem():
    frequencias = frequencia_termos(["Geração distribuída. GERAÇÃO solar não"])
    assert frequencias == {"geração": 2, "distribuída": 1, "solar": 1}


def test_sem_acento():
    assert sem_acento("Não Ação ÇÃO") == "nao acao cao"
