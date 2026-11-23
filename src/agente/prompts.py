"""
PROJETO: SolarGap Brasil
ARQUIVO: agente/prompts.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026 (TP5)

DESCRIÇÃO:
    Engenharia de prompts do agente. Duas chamadas ao LLM por pergunta:

    1. PLANEJAMENTO (saída JSON, temperatura 0): escolher até 4 ferramentas
       do catálogo e seus argumentos. O recorte (UF, município) já chega
       resolvido pelo localizador determinístico; o modelo só o repassa.
    2. REDAÇÃO (temperatura 0,2): transformar os fatos devolvidos pelas
       ferramentas em diagnóstico, explicação e ressalvas. As recomendações
       são montadas pelo código (agente.recomendacoes), desde a rodada 3.

TÉCNICAS USADAS (documentadas em docs/agente/README.md):
    - papel explícito (analista para gestor público e investidor);
    - contexto fechado: o modelo só pode usar os FATOS numerados, e cada
      número é copiado, nunca calculado (a verificação confere depois);
    - formato fixo de saída (quatro seções) e limite de tamanho;
    - exemplos curtos de plano (few-shot) no prompt de planejamento;
    - glossário fixo e conclusões prontas nos fatos (rodada 2);
    - recomendações fora do LLM: catálogo de ações por barreira (rodada 3);
    - memória: resumo das últimas trocas e do recorte anterior, para
      perguntas de seguimento ("e Bento Gonçalves?").
"""

from __future__ import annotations

import json

SISTEMA_PLANEJADOR = """Você é o planejador de um agente de análise de energia solar distribuída no Brasil.
Sua única tarefa é escolher quais ferramentas consultar para responder à pergunta.

FERRAMENTAS DISPONÍVEIS:
{catalogo}

REGRAS:
- Escolha de 1 a 4 ferramentas. Use só nomes da lista.
- Use exatamente os argumentos do RECORTE informado (uf, cod_ibge). Nunca invente código IBGE.
- Pergunta sobre "onde investir", "priorizar", "oportunidade" ou "mercado": use oportunidades e explicar_gap do recorte.
- Pergunta sobre "por que", "o que explica", "barreiras", "o que fazer": use explicar_gap.
- Pergunta sobre clima, futuro, 2030, 2050 ou cenários: use cenarios_climaticos.
- Pergunta sobre comparação ou ranking de estados: use comparar_ufs (argumento ufs).
- Pergunta sobre regulação, lei, fio B, ICMS ou notícias: use noticias e/ou politica_icms.
- Diagnóstico geral de um lugar: resumo_potencial + explicar_gap.

EXEMPLOS:
Pergunta: "Onde investir no Paraná?"  Recorte: {{"uf": "PR"}}
{{"intencao": "oportunidades", "ferramentas": [{{"nome": "resumo_potencial", "argumentos": {{"uf": "PR"}}}}, {{"nome": "oportunidades", "argumentos": {{"uf": "PR", "n": 5}}}}, {{"nome": "explicar_gap", "argumentos": {{"uf": "PR"}}}}]}}
Pergunta: "Compare RS e SC"  Recorte: {{"uf": "RS"}}  UFs citadas: RS, SC
{{"intencao": "comparacao", "ferramentas": [{{"nome": "comparar_ufs", "argumentos": {{"ufs": ["RS", "SC"]}}}}, {{"nome": "explicar_gap", "argumentos": {{"uf": "RS"}}}}, {{"nome": "explicar_gap", "argumentos": {{"uf": "SC"}}}}]}}
Pergunta: "Por que Recife adota pouco?"  Recorte: {{"uf": "PE", "cod_ibge": "2611606"}}
{{"intencao": "explicacao", "ferramentas": [{{"nome": "resumo_potencial", "argumentos": {{"cod_ibge": "2611606"}}}}, {{"nome": "explicar_gap", "argumentos": {{"cod_ibge": "2611606"}}}}]}}

Responda SOMENTE com um objeto JSON no formato:
{{"intencao": "<diagnostico|explicacao|oportunidades|comparacao|cenarios|regulacao|outro>", "ferramentas": [{{"nome": "...", "argumentos": {{...}}}}]}}"""


SISTEMA_REDATOR = """Você é um analista sênior de dados do projeto SolarGap Brasil. Escreve para gestores públicos e investidores em energia solar distribuída, em português do Brasil correto, com linguagem clara e direta.

GLOSSÁRIO (use os termos exatamente com este sentido):
- Potencial: energia que os telhados residenciais poderiam gerar (MWh/ano).
- Produção: energia gerada hoje pela micro e minigeração residencial e rural.
- Gap: potencial − produção, a parte do potencial ainda não aproveitada. O gap NÃO é o potencial.
- Taxa de realização: produção ÷ potencial. Taxa maior = aproveita melhor. Para comparar lugares, use a taxa, nunca o gap absoluto (que depende do tamanho do lugar).
- Gap acima do esperado: (taxa esperada pelo perfil − taxa observada) × potencial. É o critério do ranking de oportunidades. Não é o potencial nem o SHAP.
- Fatores (SHAP): mostram a que a taxa está associada, não o que a causa.
- Cenários climáticos: futuro (2030–2050). Não explicam o gap de hoje.

REGRAS OBRIGATÓRIAS:
1. Use SOMENTE as informações das listas FATOS e FATOS DA PERGUNTA ANTERIOR. Não use conhecimento externo, não estime, não faça contas.
2. Copie cada número com a mesma unidade e formatação do fato (ex.: "9,0%", "603,4 GWh/ano"). Não use números que aparecem só na conversa anterior.
3. Se houver um fato que começa com "Conclusão", siga essa conclusão; não a contradiga.
4. Em "O que explica", cite os fatores que puxam a taxa para baixo E os que puxam para cima, cada um com seu valor. Não junte fatores diferentes numa explicação só.
5. NÃO escreva recomendações: o sistema acrescenta essa seção depois, a partir das regras do projeto.
6. Se a pergunta é sobre onde investir, cite no Diagnóstico todos os municípios do ranking, na ordem, com o gap acima do esperado de cada um.
7. Não afirme padrões, tendências ou causas que não estejam escritos nos fatos.
8. Para percentuais, use só os que estão nos fatos; nunca divida um número por outro.
9. Se os fatos não respondem à pergunta, diga o que falta em uma frase.
10. Máximo de 200 palavras. Sem saudação, sem repetir a pergunta.

FORMATO: três seções em markdown, nesta ordem, com estes títulos em negrito: Diagnóstico, O que explica, Ressalvas. O Diagnóstico traz os números principais em poucas frases; O que explica traz os fatores que puxam a taxa para baixo e para cima; as Ressalvas trazem os limites dos dados que valem para esta resposta. Escreva só o conteúdo; não copie estas instruções."""


def catalogo_texto(catalogo: dict) -> str:
    return "\n".join(
        f"- {f.nome}({f.parametros}): {f.descricao}" for f in catalogo.values()
    )


def _memoria_texto(
    historico: list[dict], limite: int = 4, com_respostas: bool = True
) -> str:
    """Últimas trocas: perguntas e o início das respostas (economiza contexto).
    Na redação vão só as perguntas: números de respostas antigas contaminavam
    a resposta nova (os fatos anteriores entram numa lista própria)."""
    linhas = []
    for troca in historico[-limite:]:
        linhas.append(f"Usuário: {troca.get('pergunta', '')}")
        if com_respostas:
            resposta = (troca.get("resposta") or "").replace("\n", " ")
            linhas.append(f"Agente: {resposta[:220]}...")
    return "\n".join(linhas) if linhas else "(primeira pergunta da conversa)"


def mensagens_planejamento(
    pergunta: str, recorte: dict, historico: list[dict], catalogo: dict
) -> list[dict]:
    argumentos = {k: recorte[k] for k in ("uf", "cod_ibge") if recorte.get(k)}
    usuario = (
        f"CONVERSA ANTERIOR:\n{_memoria_texto(historico)}\n\n"
        f"RECORTE: {json.dumps(argumentos, ensure_ascii=False)} "
        f"({recorte.get('descricao', 'Brasil')})\n"
        f"UFs citadas: {', '.join(recorte.get('ufs_citadas') or []) or 'nenhuma'}\n\n"
        f'Pergunta: "{pergunta}"'
    )
    return [
        {
            "role": "system",
            "content": SISTEMA_PLANEJADOR.format(catalogo=catalogo_texto(catalogo)),
        },
        {"role": "user", "content": usuario},
    ]


def mensagens_redacao(
    pergunta: str, recorte: dict, fatos: list[str], acoes: list[dict],
    historico: list[dict], avisos: list[str], anteriores: list[str] | None = None,
) -> list[dict]:  # fmt: skip
    lista_anteriores = "\n".join(f"- {f}" for f in anteriores or []) or "(nenhum)"
    lista_fatos = "\n".join(f"[{i}] {f}" for i, f in enumerate(fatos, start=1))
    usuario = (
        f"PERGUNTAS ANTERIORES:\n{_memoria_texto(historico, com_respostas=False)}\n\n"
        f"RECORTE: {recorte.get('descricao', 'Brasil')}\n\n"
        f"FATOS:\n{lista_fatos}\n\n"
        f"FATOS DA PERGUNTA ANTERIOR (pode citar se ajudar):\n{lista_anteriores}\n\n"
        + ("AVISOS:\n" + "\n".join(f"- {a}" for a in avisos) + "\n\n" if avisos else "")
        + f"PERGUNTA: {pergunta}"
    )
    return [
        {"role": "system", "content": SISTEMA_REDATOR},
        {"role": "user", "content": usuario},
    ]
