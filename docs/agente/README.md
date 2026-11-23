# Agente de decisão — SolarGap Brasil (TP5)

**Autora:** Pâmela Lima Ziliotto · **Data:** 23/11/2026
**Caminho escolhido no TP5:** Opção 3, agentes inteligentes para tomada de decisão, com memória conversacional (elemento da Opção 1)
**Código:** `src/agente/` · **Painel:** página *Agente de decisão* · **API:** `POST /agente/perguntar`

---

## 1. Problema de negócio que o agente resolve

Até o TP4.5, o projeto respondia *quanto* do potencial solar residencial cada município aproveita (taxa de realização) e *a que fatores* isso está associado (SHAP). Para usar essas respostas, porém, era preciso saber navegar por quatro páginas, ler um waterfall e cruzar tabelas.

Os dois públicos do Project Charter fazem perguntas mais diretas:

- **Gestor público:** "Por que minha cidade está abaixo do esperado e o que posso fazer?"
- **Investidor ou integrador solar:** "Onde vale abrir operação no Rio Grande do Sul?"

O agente recebe essa pergunta em português e devolve um **diagnóstico com números**, os **fatores associados**, **recomendações acionáveis** e as **ressalvas**. Cada número tem rastro até a tabela da Gold de onde veio.

## 2. Arquitetura: um passo de agente por pergunta

```
pergunta ──► 1. PERCEBER   localizador determinístico de UF/município (+ memória da conversa)
          ──► 2. PLANEJAR   LLM escolhe ferramentas em JSON  │ sem LLM: regras de intenção
          ──► 3. AGIR       8 ferramentas sobre a Gold (src/servicos, o mesmo código da API)
          ──► 4. REDIGIR    LLM transforma FATOS em diagnóstico │ sem LLM: modelo de texto fixo
          ──► 5. VERIFICAR  todo número da resposta precisa estar nos fatos
```

| Ferramenta | O que consulta | Origem (TP) |
|---|---|---|
| `resumo_potencial` | potencial (x), produção (y), gap e taxa do recorte | TP4.5, Tarefa 2 |
| `explicar_gap` | contribuições SHAP agrupadas e ações por barreira | TP4.5, Tarefa 4 |
| `oportunidades` | municípios com maior *gap acima do esperado* | **novo no TP5** |
| `comparar_ufs` | ranking das UFs pela taxa de realização | TP4.5 |
| `cenarios_climaticos` | irradiação e potencial 2030–2050 (SSP2-4.5 e SSP5-8.5) | TP4.5, Tarefa 6 |
| `politica_icms` | isenção de ICMS na GD por UF | TP3 (CONFAZ) |
| `adocao_uf` | watts por habitante e posição no ranking | TP1–TP3 (ANEEL + IBGE) |
| `noticias` | notícias relevantes e resumidas do corpus | TP2–TP4 (scraping + PTT5/mDeBERTa) |

O agente usa **todo o ciclo de dados do projeto**. Coleta por API (ANEEL, IBGE, NASA POWER, CMIP6) e por scraping (EBC, gov.br, CONFAZ). Tratamento em camadas (Bronze, Silver, Gold). Modelagem (LightGBM + SHAP) e modelos de linguagem locais (resumo e relevância). O agente é a camada que transforma esse ciclo em decisão.

### Decisões de projeto

**O LLM não localiza o município.** Há 232 nomes de município repetidos no Brasil, e um modelo de 7B inventa dígitos de código IBGE. A busca é determinística, contra a própria Gold (`recortes.py`). Ela escolhe o trecho mais longo ("Pará de Minas" vence "Pará"; "Rio Grande do Sul" vence "Rio Grande"), resolve homônimos pela UF citada e avisa quando a escolha é ambígua. Se o LLM devolver outro código no plano, o agente o substitui pelo localizado.

**O LLM não faz contas.** As ferramentas devolvem *fatos*: frases curtas com os números já formatados em pt-BR ("taxa de realização de 9,0%"). O prompt de redação proíbe calcular e manda copiar. Depois, `verificacao.py` extrai cada número da resposta e confere se ele está nos fatos. Se algum número não está, a resposta sai com aviso e o painel mostra quais são. É a defesa contra a alucinação numérica, o risco central de um LLM num projeto cujo valor é o dado validado (a mesma preocupação que levou a reprovar o Qwen como resumidor no TP4).

**O LLM não inventa a recomendação.** As ações estão escritas em `ACOES_POR_FATOR`. Cada uma vale para uma família de fator SHAP que puxa a taxa para baixo **e** para o nível do fator no recorte (acima ou abaixo da mediana dos municípios). O nível importa. Em Caxias do Sul, a densidade reduz a taxa por ser *alta*: mais apartamentos, menos telhado próprio, e a ação é geração compartilhada e condomínios. Num município pequeno, ela reduz por ser *baixa*, e a ação é agrupar a demanda. A primeira versão das regras não fazia essa distinção e recomendava a ação errada para Caxias; o teste `test_acao_depende_do_nivel_do_fator` impede a regressão. Desde a rodada 3, o texto das recomendações também é montado pelo código; o LLM escreve diagnóstico, explicação e ressalvas.

**O agente funciona sem LLM.** Se o Ollama não estiver no ar, ou se o plano vier em JSON inválido, o agente usa as regras de intenção e um texto fixo. Os números e as ferramentas são os mesmos; muda só a redação. A demonstração não depende do modelo, e o modo por regras serve de linha de base na avaliação.

**Mesmo código do painel e da API.** As ferramentas chamam `src/servicos/potencial.py` e `indicadores.py` diretamente, sem HTTP. São as mesmas funções das rotas `/potencial`, então os números do agente, do painel e da API não divergem. A página do agente roda o agente no próprio processo do Streamlit (funciona sem a API no ar); a API expõe o mesmo agente em `POST /agente/perguntar`.

### Indicador novo: gap acima do esperado

O modelo explicativo da Tarefa 4 prevê a taxa que o perfil do município sugere (renda, tarifa, urbanização, agro, ICMS, irradiação). Quando a taxa observada fica abaixo da prevista, a diferença é adoção que o perfil comportaria e não aconteceu:

```
gap_acima_do_esperado (MWh/ano) = max(0, taxa_prevista − taxa_observada) × potencial (x)
```

É o critério de priorização de mercado da ferramenta `oportunidades`. Ele favorece municípios grandes, com perfil favorável e adoção atrasada, e exclui municípios com menos de 5.000 domicílios e os 19 com taxa acima de 100% (fora do treino). Na visão corrigida:

| Recorte | Municípios abaixo do esperado | Gap acima do esperado | Três primeiros |
|---|---|---|---|
| Brasil | 1.378 | 3,6 TWh/ano | Recife (PE), Brasília (DF), Salvador (BA) |
| RS | 66 | 199,4 GWh/ano | Bagé, Viamão, Caxias do Sul |

Leitura de associação, não de causa: o modelo não mede o efeito de uma ação. Esse "gap" é demanda que o perfil sugere e que pode não se realizar por razões fora do modelo (por exemplo, a proporção de apartamentos, que a densidade só aproxima).

## 3. Modelo de linguagem

| Item | Escolha | Por quê |
|---|---|---|
| Provedor padrão | **Ollama** (local) | Coerente com o TP4: roda na máquina, sem custo por chamada e sem enviar dados para fora |
| Modelo padrão | **Qwen2.5-7B-Instruct** (Q4, ~4,7 GB) | Cabe na GTX 1660 Ti de 6 GB. Segue instruções e gera JSON em português bem melhor que o 1.5B avaliado no TP4. A tarefa aqui não exige conhecimento do modelo, só escolher ferramentas e redigir a partir de fatos prontos |
| Alternativa leve | `qwen2.5:3b` (~2 GB) | Para máquinas sem GPU dedicada |
| Alternativa online | qualquer API compatível com OpenAI | O TP5 permite API online; basta trocar três variáveis de ambiente |

Por que não usar o modelo do TP4: o PTT5 e o mDeBERTa são modelos de tarefa (resumo e classificação). Eles não seguem instruções nem produzem um plano em JSON. Continuam em uso dentro do agente, de forma indireta: a ferramenta `noticias` lê o corpus já filtrado pela relevância (mDeBERTa) e resumido (PTT5).

**Configuração** (variáveis de ambiente):

```bash
SOLARGAP_LLM_PROVEDOR=ollama        # ollama | openai | nenhum
SOLARGAP_LLM_MODELO=qwen2.5:7b
SOLARGAP_LLM_URL=http://localhost:11434
SOLARGAP_LLM_API_KEY=...            # só para o provedor openai
SOLARGAP_LLM_TIMEOUT=120
```

## 4. Engenharia de prompts

São duas chamadas por pergunta (`src/agente/prompts.py`):

**Planejamento** (JSON, temperatura 0). O prompt traz o catálogo de ferramentas com os argumentos, regras de uso por tipo de pergunta, dois exemplos completos (*few-shot*) e o recorte já resolvido. O modelo só repassa o recorte, nunca o inventa. A saída é validada: ferramenta fora do catálogo é descartada; argumento desconhecido é removido; o recorte é sobrescrito pelo localizado.

**Redação** (temperatura 0,2, máximo de 230 palavras). O prompt traz:

- **papel:** analista sênior escrevendo para gestor público e investidor;
- **contexto fechado:** só os FATOS numerados, cada número copiado com a mesma formatação, sem contas;
- **catálogo de ações:** escolher e adaptar, sem criar ações novas;
- **formato fixo:** Diagnóstico, O que explica, Recomendações e Ressalvas;
- **regra de honestidade:** "associação, não causalidade" sempre que citar o SHAP; dizer o que falta quando os fatos não respondem;
- **memória:** as últimas quatro trocas (pergunta e início da resposta) entram nas duas chamadas.

**Memória conversacional.** O servidor não guarda sessão. O painel (em `st.session_state`) ou o cliente da API envia o histórico e o `contexto` da resposta anterior. Uma pergunta sem lugar citado ("E os cenários climáticos?") herda o recorte da conversa, e a resposta informa `recorte_herdado: true`. Citar "Brasil" encerra a herança.

## 5. Avaliação

`python -m src.agente.avaliacao` roda 15 perguntas com gabarito (recorte, ferramenta obrigatória), três delas de seguimento, que só se resolvem com memória. Com `--llm`, repete com o modelo configurado.

| Métrica | Regras | LLM rodada 1 | LLM rodada 2 | LLM rodada 3 | LLM rodada 3.1 |
|---|---|---|---|---|---|
| Recorte correto | 100% | 100% | 100% | 100% | 100% |
| Ferramenta correta | 100% | 100% | 100% | 100% | 100% |
| Números verificados (média) | 100% | 98,8% | 99,4% | 100% | 99,5% |
| Respostas com número fora dos dados | 0 | 2 de 15 | 1 de 15 | 0 de 15 | 1 de 15 |
| Respostas com rótulo trocado | — | — | — | — | 1 de 15 |
| Tempo médio por pergunta | < 0,1 s | 33,5 s (p95 89,7 s) | 29,5 s (p95 47,2 s) | 23,1 s (p95 36,7 s) | 23,0 s (p95 34,7 s) |

**Rodada 2 (22/11/2026).** A rodada 1 com o LLM real acertou recorte e ferramentas em 100%, mas errou o raciocínio no texto: chamou o potencial total de gap, atribuiu o ranking de oportunidades ao SHAP, considerou mais eficiente o estado com taxa menor e disse que a redução futura de irradiação explica o gap atual. Os dois números fora dos dados que deu para rastrear eram números verdadeiros, trazidos da pergunta anterior. Correções: (1) as conclusões que o modelo errava passaram a vir prontas nos fatos (quem está à frente numa comparação, que o clima futuro não explica o gap de hoje, o critério do ranking); (2) glossário fixo no prompt de redação; (3) os fatos da pergunta anterior entram numa lista própria e são aceitos pela verificação no mesmo recorte, e as respostas antigas saíram do prompt. Na rodada 2, os quatro erros de raciocínio da rodada 1 não se repetiram, e o número trazido da pergunta anterior deixou de gerar aviso. Persistem três problemas: (a) o modelo calcula percentuais por conta própria e erra a conta (o gap de Caxias do Sul descrito como 90,5% e 91,1% do potencial, quando o certo é 91,0%), o que a verificação sinalizou nas duas vezes; (b) no seguimento sobre cenários climáticos, o gap total de Caxias do Sul (603,4 GWh/ano) foi chamado de "gap acima do esperado" (que é 12,2 GWh/ano), e a resposta concluiu que "fatores socioeconômicos são os principais responsáveis", o que os dados não dizem; (c) algumas recomendações contrariam os fatores ou não são alavancas de negócio ("desenvolver projetos rurais" num estado de agropecuária baixa, "aumentar a renda média"). Os erros de rótulo e de conclusão passam pela verificação, que só confere números. Lição: com um modelo de 7B, o raciocínio quantitativo fica no código e o modelo só redige.

**Rodada 3 (23/11/2026).** Correções: (1) o fato de resumo traz pronto "O gap equivale a X% do potencial", e o prompt proíbe dividir números e afirmar padrões que não estejam nos fatos; (2) a seção Recomendações passou a ser montada pelo código, a partir de `ACOES_POR_FATOR` e, em "onde investir", do ranking (numa comparação, as ações alternam entre as UFs); o LLM escreve só Diagnóstico, O que explica e Ressalvas, e recomendações que ele escreva são substituídas; (3) a verificação confere o rótulo "gap acima do esperado" junto com o número (`verificar_rotulos`); (4) ordinais ("1º") não contam mais como número. Resultado: o percentual do gap saiu certo (91,0% em Caxias do Sul), as recomendações contraditórias sumiram, o padrão "densidade acima da mediana tem maiores gaps" não se repetiu e nenhuma resposta da avaliação trouxe número fora dos dados. O aviso de rótulo funcionou: disparou quando o modelo chamou de "gap acima do esperado" a diferença de -1,8 p.p. da taxa de Caxias do Sul e também acusa os 159,1 GWh/ano de gap total de Bento Gonçalves chamados de "gap acima do esperado" num seguimento da avaliação (conferido à parte, porque o CSV da avaliação grava os números fora dos dados, mas não os avisos de rótulo). Persistem: (a) a troca de rótulo continua acontecendo, agora sinalizada; (b) no seguimento sobre cenários climáticos, a resposta ainda não traz nenhum número da projeção e ainda conclui, sem base nos dados, que o gap "é socioeconômico"; (c) "irradiança" no lugar de "irradiação" e, na comparação RS x SC, valores de SHAP atribuídos ao fator errado (os números conferem, a associação número–fator não). Erros novos: (d) o modelo escreveu que a taxa do RS (14,0%) está "abaixo" da média brasileira (10,4%); (e) num seguimento de cenários, copiou as instruções do modelo de resposta ("2 ou 3 frases com os números principais"), e os números dessas instruções viraram aviso; (f) o aviso de rótulo deu um falso positivo ("66 municípios com gap acima do esperado", frase correta); (g) quando a pergunta não gera nenhuma ação (cenários, ranking de estados, notícias, ICMS, situação geral de uma UF sem fator negativo), a seção Recomendações fica de fora: 6 das 15 respostas da avaliação têm três seções.

**Rodada 3.1 (23/11/2026).** A rodada 3 revelou bugs do próprio código, não do modelo: (1) a seção Recomendações sumia quando a pergunta não gerava ação de fator; agora cada ferramenta tem um passo seguinte padrão (clima, comparação entre estados, ICMS, regulação, próximo passo); (2) as instruções de formato do prompt de redação tinham números ("2 ou 3 frases") que o modelo copiava; agora não têm número e pedem para não copiar as instruções; (3) o aviso de rótulo disparava em contagens ("66 municípios com gap acima do esperado"); agora só olha medidas (GWh, MWh, TWh, p.p., %). Além disso, o fato de resumo diz se a taxa está acima ou abaixo da média nacional, a mesma ação em duas UFs vira um item só e a avaliação grava os avisos e conta as respostas com rótulo trocado. Resultado: recorte e ferramenta em 100%, 99,5% dos números verificados, tempo médio de 23,0 s (p95 34,7 s). As 15 respostas têm a seção Recomendações; em 14 ela fica entre O que explica e Ressalvas, e na pergunta "Quais municípios priorizar no Brasil?" o modelo usou títulos `#` em vez de negrito, e o bloco do código foi parar depois das Ressalvas. Nenhuma resposta copiou as instruções do prompt, e a comparação com a média nacional saiu certa em todas. O seguimento sobre cenários agora traz número da projeção (-1,0% de irradiação até 2050). Uma resposta teve número fora dos dados e rótulo trocado: em Pará de Minas, o modelo calculou um "gap acima do esperado de 1,4 GWh/ano" que não está nos dados (o aviso de rótulo também marcou o 12,6% da taxa esperada, colado à expressão, que é falso alarme). Persistem como erros de redação: "o gap é socioeconômico" nas respostas de cenários, "irradiança" na comparação RS x SC, um "gap acima do esperado" dado em pontos percentuais por extenso (que a checagem, presa à sigla "p.p.", não pegou) e, em Mato Grosso, a taxa de 47,5% descrita como "abaixo do esperado" (44,7%). Depois da avaliação, duas correções na verificação (pontos percentuais por extenso; % fora da checagem de rótulo), na posição das recomendações (títulos com #) e no fato de explicação (acima/abaixo do esperado escrito); sem nova rodada com o LLM. Aqui encerramos os ajustes: os erros que sobram são de redação e estão nas Limitações.

Saídas: `docs/agente/avaliacao_regras.csv` e `docs/agente/avaliacao_llm.csv`.

**Leitura honesta.** As regras de intenção foram escritas olhando estas mesmas perguntas, então os 100% do modo por regras são uma linha de base, não prova de generalização. O que a avaliação mostra de fato:

1. o localizador e as ferramentas acertam o recorte e os dados, inclusive com memória;
2. com o LLM, a comparação relevante é a taxa de números verificados (o LLM introduz número que não está nos dados?) e o tempo;
3. a qualidade do texto do LLM em relação ao modo por regras é julgamento humano. Basta ler as duas versões lado a lado no painel (botão *Usar modelo de linguagem*).

**Testes automatizados** (`tests/test_agente.py`, `tests/test_api_agente.py`, 61 testes, sem rede): localizador (homônimos, siglas, trecho mais longo), todas as ferramentas, coerência do gap acima do esperado, ação dependente do nível do fator, plano por regras por intenção, memória, visão ANEEL, extração e verificação de números. Também cobrem o LLM simulado (um Ollama falso com `httpx.MockTransport`): o plano com código IBGE errado é corrigido e a ferramenta inventada é descartada; o número inventado gera aviso; o JSON inválido cai nas regras; o serviço fora do ar não quebra.

## 6. Limitações

- **Associação, não causalidade.** As recomendações vêm de fatores associados à taxa no modelo explicativo. Não medem o efeito de uma política ou de uma campanha.
- **Escopo residencial e rural.** O potencial é o dos telhados residenciais, com premissas fixas (15 m², 20%, PR 0,75). Comércio, indústria e usinas de minigeração ficam fora da métrica.
- **Regras de ação escritas à mão.** São plausíveis e revisáveis, mas não foram validadas com especialistas do setor. Revisá-las com um integrador solar é o próximo passo natural.
- **Localizador por nome exato.** Erros de digitação ("Caxia do Sul") não são corrigidos; o agente responde no nível da UF ou do Brasil e avisa.
- **Uma rodada de ferramentas por pergunta.** O agente não encadeia raciocínio em várias etapas (por exemplo, achar as oportunidades e depois explicar cada uma). Para manter tempo e previsibilidade num modelo local, a explicação de cada município é uma pergunta de seguimento.
- **Erros de redação do LLM ainda presentes.** Depois da rodada 3.1: troca do rótulo "gap acima do esperado" (sinalizada por aviso quando vem com GWh, MWh, TWh, "p.p." ou %, mas não com "pontos percentuais" por extenso), conta feita pelo próprio modelo apesar da proibição, conclusão sem base ("o gap é socioeconômico"), comparação invertida com a taxa esperada, "irradiança" no lugar de "irradiação" e, quando o modelo usa títulos `#` em vez de negrito, a seção Recomendações fica depois das Ressalvas. A verificação confere números e o rótulo 'gap acima do esperado'; erros de raciocínio sem número (uma conclusão sem base, por exemplo) não são detectados automaticamente.
- **Memória curta.** As últimas quatro perguntas entram no prompt de planejamento com o início das respostas; no prompt de redação entram só as perguntas e os fatos da pergunta anterior (no mesmo recorte), para caber na janela de 8.192 tokens e não trazer números de respostas antigas.
