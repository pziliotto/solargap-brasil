"""
PROJETO: SolarGap Brasil
ARQUIVO: agente/avaliacao.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026 (TP5)

DESCRIÇÃO:
    Avaliação do agente com um conjunto fixo de perguntas com gabarito
    (recorte esperado, intenção esperada, ferramenta obrigatória), inclusive
    perguntas de seguimento que só se resolvem com memória.

MÉTRICAS POR PERGUNTA:
    recorte_ok      o agente identificou a UF/município certo
    ferramenta_ok   a ferramenta obrigatória foi usada
    numeros_ok      fração dos números da resposta presentes nos fatos
    tempo_s         tempo total da pergunta

USO (a partir da raiz):
    python -m src.agente.avaliacao            # modo por regras (linha de base)
    python -m src.agente.avaliacao --llm      # com o LLM configurado (Ollama)

SAÍDA:
    docs/agente/avaliacao_<modo>.csv e um resumo no terminal.
"""

from __future__ import annotations

import argparse
import time

import pandas as pd

from src.agente.agente import Agente
from src.agente.llm import ClienteLLM, ConfigLLM
from src.data_acquisition.coletor_base import obter_project_root

PASTA_SAIDA = obter_project_root(__file__) / "docs" / "agente"

# (pergunta, descrição do recorte esperado, ferramenta obrigatória, seguimento?)
CASOS = [
    ("Por que Caxias do Sul está abaixo do esperado e o que fazer?", "Caxias do Sul (RS)", "explicar_gap", False),
    ("E Bento Gonçalves?", "Bento Gonçalves (RS)", "resumo_potencial", True),
    ("E os cenários climáticos para lá?", "Bento Gonçalves (RS)", "cenarios_climaticos", True),
    ("Onde investir em geração distribuída no Rio Grande do Sul?", "Rio Grande do Sul", "oportunidades", False),
    ("Quais municípios priorizar no Brasil?", "Brasil", "oportunidades", False),
    ("Compare RS e SC", "Rio Grande do Sul", "comparar_ufs", False),
    ("Quais estados têm as maiores taxas de realização?", "Brasil", "comparar_ufs", False),
    ("Por que Recife adota tão pouca energia solar?", "Recife (PE)", "explicar_gap", False),
    ("Como fica o potencial de Recife nos cenários até 2050?", "Recife (PE)", "cenarios_climaticos", False),
    ("O que dizem as notícias sobre o fio B?", "Brasil", "noticias", False),
    ("Desde quando a Bahia tem isenção de ICMS na geração distribuída?", "Bahia", "politica_icms", False),
    ("Como está Mato Grosso?", "Mato Grosso", "resumo_potencial", False),
    ("Qual o mercado em Pará de Minas?", "Pará de Minas (MG)", "oportunidades", False),
    ("Bom Jesus no RS tem espaço para crescer?", "Bom Jesus (RS)", "resumo_potencial", False),
    ("Qual a situação de Salvador?", "Salvador (BA)", "explicar_gap", False),
]  # fmt: skip


def avaliar(agente: Agente, usar_llm: bool) -> pd.DataFrame:
    linhas = []
    historico: list[dict] = []
    contexto: dict = {}
    for pergunta, recorte_esperado, ferramenta, seguimento in CASOS:
        if not seguimento:
            historico, contexto = [], {}
        inicio = time.perf_counter()
        r = agente.perguntar(pergunta, historico, contexto, usar_llm=usar_llm)
        usadas = [f["nome"] for f in r.ferramentas]
        linhas.append(
            {
                "pergunta": pergunta,
                "seguimento": seguimento,
                "modo": r.modo,
                "recorte_esperado": recorte_esperado,
                "recorte_obtido": r.recorte["descricao"],
                "recorte_ok": r.recorte["descricao"] == recorte_esperado,
                "ferramenta_esperada": ferramenta,
                "ferramentas_usadas": ", ".join(usadas),
                "ferramenta_ok": ferramenta in usadas,
                "numeros": r.verificacao["numeros"],
                "numeros_ok": round(r.verificacao["taxa"], 3),
                "nao_encontrados": ", ".join(r.verificacao["nao_encontrados"]),
                "palavras": len(r.resposta.split()),
                "rotulos_trocados": sum("tem outro significado" in a for a in r.avisos),
                "avisos": " | ".join(r.avisos),
                "resposta": r.resposta,
                "tempo_s": round(time.perf_counter() - inicio, 2),
            }
        )
        historico.append({"pergunta": pergunta, "resposta": r.resposta})
        contexto = r.contexto
    return pd.DataFrame(linhas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm", action="store_true", help="usa o LLM configurado")
    args = parser.parse_args()
    cliente = ClienteLLM() if args.llm else ClienteLLM(ConfigLLM(provedor="nenhum"))
    if args.llm and not cliente.disponivel():
        raise SystemExit(
            f"LLM indisponível ({cliente.config.descricao} em {cliente.config.url}). "
            f"Rode: ollama pull {cliente.config.modelo}"
        )
    agente = Agente.carregar(cliente)
    tabela = avaliar(agente, usar_llm=args.llm)
    nome = "llm" if args.llm else "regras"
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    saida = PASTA_SAIDA / f"avaliacao_{nome}.csv"
    tabela.to_csv(saida, index=False, encoding="utf-8")
    print(f"Modo: {nome} ({cliente.config.descricao if args.llm else 'sem LLM'})")
    print(f"Recorte correto:      {tabela['recorte_ok'].mean():.0%}")
    print(f"Ferramenta correta:   {tabela['ferramenta_ok'].mean():.0%}")
    print(
        f"Números verificados:  {tabela['numeros_ok'].mean():.1%} (média por resposta)"
    )
    print(f"Respostas com número fora dos dados: {(tabela['numeros_ok'] < 1).sum()}")
    print(
        f"Respostas com rótulo trocado:        {(tabela['rotulos_trocados'] > 0).sum()}"
    )
    print(
        f"Tempo médio:          {tabela['tempo_s'].mean():.1f} s (p95 {tabela['tempo_s'].quantile(0.95):.1f} s)"
    )
    print(f"Arquivo: {saida.relative_to(obter_project_root(__file__))}")


if __name__ == "__main__":
    main()
