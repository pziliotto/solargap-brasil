# Escolha dos modelos de linguagem — SolarGap Brasil (TP4)

**Autora:** Pâmela Lima Ziliotto
**Data:** 16/11/2026 · **Atualização:** 22/11/2026 (benchmark v2 da relevância e do tom, seção 9; estratégia híbrida adotada na seção 9.6)
**Evidência:** `docs/benchmark/` (rótulos, saídas de cada modelo e métricas)

---

## 1. Decisão

| Tarefa | Modelo | Situação |
|---|---|---|
| Resumo | [`recogna-nlp/ptt5-base-summ`](https://huggingface.co/recogna-nlp/ptt5-base-summ) | **Adotado** — gravado no corpus e exposto na API, exceto para as fontes CC BY-ND (ANEEL, MME, Agência Gov), que não recebem resumo |
| Relevância (a notícia trata de energia solar?) | [`MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7), zero-shot | **Adotado com ressalva** — filtro do corpus, com a probabilidade sempre visível. **Desde 22/11/2026, estratégia híbrida:** termo de geração distribuída no título OU probabilidade de pelo menos 0,4 (seção 9.6) |
| Tom (favorável, desfavorável, neutro) | mesmo mDeBERTa, zero-shot | **Reprovado** (confirmado no benchmark v2) — fica na API como experimental; não é gravado nem exibido como indicador |

Os dois modelos rodam localmente com Transformers/PyTorch, juntos ocupam cerca de 1,7 GB de memória de GPU e não dependem de serviço externo depois do primeiro download.

## 2. Por que modelos de tarefa e não um chatbot

O enunciado pede um modelo adequado à tarefa, considerando desempenho, custo local e acessibilidade, e cita BERT e T5 como exemplos. Para resumir e classificar notícias, modelos especializados são menores, mais rápidos e mais previsíveis. Um LLM generativo pequeno tende a acrescentar números e nomes que não estão no texto, o que é grave num projeto cujo valor está no dado validado.

Essa preferência não foi assumida: um LLM generativo (Qwen2.5-1.5B-Instruct) entrou no benchmark como candidato, e a escolha saiu da medição.

## 3. Como foi medido

**Hardware.** NVIDIA GeForce GTX 1660 Ti (6 GB), 32 GB de RAM, Windows. PyTorch 2.15 com CUDA 13.2.

**Resumo — 56 notícias** (corpus de 141; com o corpus de 553, a mesma regra daria 356, ver seção 9.5). A referência é a linha fina escrita pela redação, que funciona como um resumo humano. Para não haver vazamento, o modelo recebe título e texto **sem** a linha fina, e ficam de fora as notícias em que a "linha fina" é apenas o primeiro parágrafo repetido. A linha de base é o início do texto com o mesmo número de palavras da referência (o "lide"). Métrica: ROUGE-1 e ROUGE-L (F1), com tokenização que preserva acentos (`src/ia/metricas.py`).

**Classificação — 30 notícias rotuladas à mão.** Amostra estratificada por fonte e período (`src/ia/rotulagem.py`), rotulada seguindo o guia de `docs/benchmark/README.md`: 23 relevantes e 7 fora do tema; entre as relevantes, 19 favoráveis, 2 desfavoráveis e 2 neutras. Métricas: acurácia e F1 macro, que não deixa a classe mais frequente esconder as demais.

**Linha de base de classe majoritária.** Com classes tão desequilibradas, um "modelo" que responde sempre a classe mais comum já parece bom. Todo resultado é comparado a ele.

**Custo.** Tempo de carga, tempo médio e p95 por notícia (depois de uma execução de aquecimento), memória do processo e pico de memória da GPU.

## 4. Resultados

### 4.1 Resumo

| Modelo | Parâmetros | ROUGE-1 | ROUGE-L | Palavras | Tempo/notícia (GPU) | VRAM pico | Licença |
|---|---|---|---|---|---|---|---|
| Linha de base (lide) | — | 0,309 | 0,262 | 28 | — | — | — |
| **ptt5-base-summ** | 223 M | **0,344** | **0,281** | 37 | 1,9 s | 1,1 GB | MIT |
| ptt5-base-summ-xlsum | 223 M | 0,240 | 0,175 | 25 | 1,4 s | 1,0 GB | CC BY-NC-SA 4.0 |
| Qwen2.5-1.5B-Instruct | 1.544 M | 0,284 | 0,197 | 63 | 10,9 s | 3,1 GB | Apache-2.0 |

- **O PTT5-summ é o único que supera o lide**, e por margem pequena (+3,5 pontos de ROUGE-1). Em notícia, o início do texto já é um resumo forte (pirâmide invertida); superar essa linha de base é o mínimo para justificar o custo.
- **O XL-Sum resume pior que copiar o início.** Ajustado em notícias da BBC, gera frases curtas no estilo de manchete, distantes das linhas finas brasileiras.
- **O Qwen é 6 vezes mais lento, usa 3 vezes mais memória e resume pior.** Os resumos saem longos (63 palavras), muitas vezes em tópicos, e com detalhes numéricos que não fazem parte da referência. Na GTX 1660 Ti ele só coube em meia precisão (fp16).

### 4.2 Relevância

| Modelo | Acurácia | F1 macro | Tempo/notícia (GPU) | VRAM pico |
|---|---|---|---|---|
| Linha de base (sempre "sim") | 0,767 | 0,434 | — | — |
| **mDeBERTa-v3-base (NLI)** | 0,767 | **0,713** | 0,84 s* | 0,7 GB |
| MiniLMv2-L6 (NLI) | 0,600 | 0,375 | 0,04 s* | 0,4 GB |

\* Tempo de relevância e tom juntos (quatro inferências por notícia).

- **O mDeBERTa tem a mesma acurácia da linha de base, mas F1 macro bem maior** (0,71 contra 0,43): ele de fato separa as duas classes, enquanto a linha de base nunca acerta uma notícia fora do tema. Acertou 5 das 7 fora do tema.
- **As probabilidades são polarizadas** (mediana de 0,999 nas relevantes e 0,213 nas demais), então mudar o limiar de 0,5 não resolveria os erros.
- **O MiniLM não serve:** classificou todas as 7 notícias fora do tema como relevantes.

**Análise dos erros do mDeBERTa (7 de 30).**

| Notícia | Rótulo | Probabilidade | Leitura |
|---|---|---|---|
| Fontes renováveis responderam por quase 88% da energia gerada | relevante | 0,005 | Renováveis em geral |
| ONU pede fim do financiamento ao carvão e apoio à renovável | relevante | 0,001 | Renováveis em geral |
| Especialistas divergem sobre uso da energia nuclear | relevante | 0,000 | Outra fonte como assunto principal |
| Plataforma que certifica energia renovável | relevante | 0,004 | Renováveis em geral |
| ANEEL multa Neoenergia Coelba por irregularidades na GD | relevante | 0,000 | **Erro claro**: trata de geração distribuída sem usar a palavra "solar" |
| Hidrelétrica do Tapajós pode ser leiloada | fora do tema | 1,000 | **Erro claro** |
| Regime de tributação para datacenter | fora do tema | 0,514 | Caso limite |

Quatro dos cinco falsos negativos são notícias sobre renováveis em geral, que a rotulagem considerou relevantes. O modelo aplica o critério de forma mais estrita que a rotuladora; com outro rotulador, parte desses casos poderia mudar de lado. Restam dois erros claros. Os rótulos não foram alterados depois de ver as previsões, para não ajustar o gabarito ao modelo.

### 4.3 Tom

| Modelo | Acurácia | F1 macro |
|---|---|---|
| Linha de base (sempre "favorável") | **0,826** | 0,302 |
| mDeBERTa-v3-base (NLI) | 0,435 | 0,276 |
| MiniLMv2-L6 (NLI) | 0,696 | 0,366 |

- **Nenhum candidato supera a linha de base em acurácia.** O mDeBERTa classificou 11 das 19 notícias favoráveis como neutras e nenhuma como desfavorável; acertou as 2 neutras, mas também chamou as 2 desfavoráveis de neutras.
- **O F1 macro do MiniLM é maior** porque ele chuta "desfavorável" com frequência (5 vezes, 1 acerto), mas sua acurácia segue abaixo da linha de base.
- **Com 4 notícias fora da classe favorável, a métrica é instável**: um acerto a mais ou a menos muda o F1 macro inteiro.

**Por que o tom é difícil aqui.** Notícia de agência pública tem linguagem institucional e descritiva; a distinção entre "relata avanço" e "apenas informa" é sutil até para uma pessoa, e o corpus é quase todo de notícias de avanço. Um classificador zero-shot genérico não captura essa nuance.

**Decisão.** Gravar no corpus um rótulo que erra mais que um chute constante daria aparência de dado a algo que não é. O tom continua disponível em `POST /processar_texto` para demonstração, sempre com `experimental: true` e um aviso com este resultado.

## 5. Custo computacional local

| Item | GPU (GTX 1660 Ti) | CPU |
|---|---|---|
| Resumo (PTT5), por notícia | 1,9 s (p95 2,8 s) | 4,9 s (p95 7,5 s) |
| Relevância + tom (mDeBERTa), por notícia | 0,8 s | 49,2 s (p95 53,3 s) |
| Carga dos dois modelos | ~11 s | ~11 s |
| Memória de GPU | 1,1 GB + 0,7 GB | — |
| Memória do processo | ~4,7 GB (os dois modelos e o PyTorch) | ~4,7 GB |

**Nota sobre CPU.** Medido com `python -m src.ia.benchmark --dispositivo cpu`, o resumo fica em 4,9 s por notícia e a relevância + tom em 49,2 s, então a aplicação funciona sem GPU, mas o mDeBERTa em CPU só é viável em lote, não em uso interativo. Em CPU, pedir relevância e tom na mesma chamada da API pode passar do limite de 60 s e receber 504; aumente SOLARGAP_TIMEOUT_INFERENCIA ou peça só a relevância (cerca de um quarto desse tempo).

**Consequência para o projeto.** O processamento do corpus inteiro (119 notícias) leva cerca de 5 minutos na GPU. Por isso ele roda **em lote** (`python -m src.ia.processar_corpus`) e o resultado vai para o Git (`data/processed/corpus_ia.csv`). Quem avalia o projeto vê resumos e relevância sem GPU e sem baixar 2 GB de modelos.

## 6. Acessibilidade

- **Distribuição:** os dois modelos estão no HuggingFace Hub e são baixados automaticamente na primeira carga para o cache local. Depois disso, com `HF_HUB_OFFLINE=1`, nada mais acessa a rede.
- **Licenças:** MIT nos dois modelos adotados, compatível com o repositório público. O PTT5-XL-Sum (não comercial) e o Qwen (Apache-2.0) foram apenas avaliados.
- **Idioma:** o PTT5 foi pré-treinado em português brasileiro (corpus BrWaC) e ajustado em notícias brasileiras (RecognaSumm). O mDeBERTa foi ajustado em NLI em 27 idiomas, inclusive português.
- **Janela de 512 tokens:** 64% das notícias passam do limite no resumo e 80% na classificação. O modelo lê o início, onde o texto jornalístico concentra o essencial, e toda resposta da API informa `truncado: true` quando isso acontece.

## 7. Limitações

- **Amostras pequenas:** 30 notícias rotuladas e 56 referências de resumo. O benchmark descarta candidatos claramente piores e mede custo; não crava o melhor modelo por décimos.
- **Um único rotulador.** Sem uma segunda rotulagem não há medida de concordância entre pessoas, que seria o teto realista para os modelos.
- **ROUGE mede sobreposição de palavras, não fidelidade.** Os resumos de `docs/benchmark/saidas_resumo_cuda.csv` foram lidos; o PTT5 às vezes inverte sujeito e verbo ("Redata sanciona Regime..."), por isso o painel sempre mostra o link da matéria original ao lado do resumo.
- **A hipótese de relevância fala só em "energia solar".** No lote do corpus, o modelo julgou fora do tema notícias de geração distribuída que não usam a palavra "solar" (multa à Coelba, revisão das regras para quem gera a própria energia, impacto da geração própria nas distribuidoras). Por isso o filtro do painel vem desligado por padrão. No benchmark v2 (seção 9), hipóteses com "geração distribuída" superdispararam. O problema foi resolvido com a estratégia híbrida (termo de GD no título OU zero-shot), adotada na seção 9.6.

## 8. Ligação com o TP5

A relevância filtra o que o agente do TP5 vai ler, e o resumo reduz o contexto que ele precisa consumir. O tom, que os modelos locais não resolveram, é candidato natural para o LLM online permitido no TP5. A relevância de GD sem "solar", que o zero-shot também não resolveu (seção 9), é outro. Os rótulos de desenvolvimento servem para ajustes. O teste congelado (`docs/benchmark/teste_real_congelado.csv`) já foi usado uma vez: uma avaliação final no TP5 precisa de um novo conjunto de teste ou deve declarar o reuso.

## 9. Benchmark v2 da relevância e do tom (22/11/2026)

Código: `src/ia/benchmark_relevancia.py`. Arquivos: `docs/benchmark/` (seção "Benchmark v2" do README).

### 9.1 Dados e divisão

- **Gabarito:** os 30 rótulos do v1 mais as 120 notícias da planilha v2, rotuladas pela autora com o mesmo guia. Saem as 2 notícias do v1 descobertas por caminho proibido pelo `robots.txt`. Ficam 148 notícias: 106 relevantes e 42 fora do tema.
- **Divisão:** 40% para desenvolvimento (59 notícias) e 60% para teste (89), estratificada por rótulo, fonte e flag "GD sem solar", com semente fixa.
- **Teste congelado:** o teste está em `teste_real_congelado.csv`, e o SHA-256 do arquivo é conferido por um teste automatizado. Ele foi avaliado **uma única vez**, e a etapa recusa uma segunda execução.
- **Subconjunto GD sem "solar" sobre-representado de propósito.** São notícias que mencionam geração distribuída, micro ou minigeração, Lei 14.300 ou fio B sem citar "solar" nem "fotovoltaica". Elas são 23% do gabarito (34 de 148) e 24% do teste (21 de 89), contra 14% do corpus (80 de 553) e quase nenhuma nas agências da EBC (2 de 141). A planilha v2 reservou uma cota para esse caso porque é nele que a hipótese atual falha. Por isso, as métricas gerais deste benchmark **não estimam** o desempenho no corpus como um todo.
- **Proporção de "sim" alta por construção.** Todo o corpus passou pelo filtro de palavras da coleta, e por isso 72% do teste é relevante. Nessa situação, responder sempre "sim" já dá F1 de 0,84 na classe "sim". Essa referência trivial entra em todas as comparações.

### 9.2 Desenvolvimento: estratégias e limiares

Foram testadas quatro estratégias, com limiares de 0,30 a 0,70:

- **a) atual:** "Esta notícia trata de energia solar."
- **b) ampla:** "Esta notícia trata de energia solar, geração distribuída ou micro e minigeração de energia."
- **c) curtas:** a maior probabilidade entre três hipóteses: a atual, "…geração distribuída de energia." e "…Lei 14.300 ou da compensação de energia elétrica."
- **d) híbrido:** um termo de GD do vocabulário (no título ou em qualquer campo) OU a hipótese atual.

A tabela mostra o melhor limiar de cada estratégia, com métricas da classe "sim". São 59 notícias, 13 delas de GD sem "solar". A tabela completa está em `relevancia_desenvolvimento.csv`.

| Estratégia | Limiar | Precisão | Recall | F1 | F1 GD sem "solar" |
|---|---|---|---|---|---|
| Referência: sempre "sim" | — | 0,712 | 1,000 | 0,832 | 0,700 |
| a) atual (configuração em uso) | 0,50 | 0,903 | 0,667 | 0,767 | 0,000 |
| a) atual | 0,30–0,40 | 0,906 | 0,690 | 0,784 | 0,000 |
| b) ampla | 0,35 | 0,810 | 0,810 | 0,810 | 0,545 |
| **c) curtas** | **0,40–0,60** | 0,737 | 1,000 | **0,848** | **0,737** |
| d) híbrido, termo no texto | 0,30–0,40 | 0,804 | 0,881 | 0,841 | 0,700 |
| d) híbrido, termo no título | 0,30–0,40 | 0,892 | 0,786 | 0,835 | 0,667 |

Por fonte, com limiar de 0,5:

| Fonte | n | atual: F1 | curtas: F1 |
|---|---|---|---|
| ANEEL | 30 | 0,52 | 0,74 |
| Agência Brasil | 18 | 0,90 | 0,94 |
| MME | 9 | 0,94 | 1,00 |
| Agência Gov | 2 | 0,00 | 0,00 |

**Escolha:** c) curtas, com limiar 0,5. A regra de escolha foi definida antes da execução: maior F1 geral, depois maior F1 em GD sem "solar", depois menor custo e, por fim, o limiar mais perto de 0,5.

**Ressalva identificada no desenvolvimento.** A hipótese de GD ("…geração distribuída de energia.") dá probabilidade alta a quase qualquer notícia sobre geração de eletricidade: a mediana é 0,98 nas notícias fora do tema. Por isso as curtas acertaram só 2 dos 17 "não" e ficaram a 0,016 de F1 do "sempre sim". Diante disso, antes de abrir o teste, a condição de adoção passou a exigir que a escolhida vencesse **também** o "sempre sim", como já se exige do tom. A condição ficou registrada em `relevancia_escolha.json` antes da avaliação.

### 9.3 Teste congelado: primeira consulta

> Primeira consulta, com o critério de escolha F1-sim, que estava errado. A métrica foi corrigida na seção 9.6, que traz a segunda consulta e a decisão em vigor.

F1 da classe "sim", com IC 95% por bootstrap (1.000 reamostragens, percentis). As diferenças são pareadas, calculadas nas mesmas reamostragens.

| Configuração | Geral (n = 89, 64 "sim"): precisão / recall | F1 [IC 95%] | GD sem "solar" (n = 21, 12 "sim"): F1 [IC 95%] |
|---|---|---|---|
| Atual (a, limiar 0,5) | 0,778 / 0,656 | 0,712 [0,628; 0,800] | 0,000 [0,000; 0,000] |
| Escolhida (c, limiar 0,5) | 0,724 / 0,984 | 0,834 [0,764; 0,892] | 0,727 [0,500; 0,865] |
| Sempre "sim" | 0,719 / 1,000 | 0,837 [0,764; 0,894] | 0,727 [0,500; 0,865] |

| Diferença pareada de F1 | Geral [IC 95%] | GD sem "solar" [IC 95%] |
|---|---|---|
| Escolhida − atual | +0,123 [0,035; 0,208] | +0,727 [0,500; 0,865] |
| Escolhida − sempre "sim" | −0,002 [−0,022; 0,016] | 0,000 [0,000; 0,000] |
| Atual − sempre "sim" | −0,125 [−0,210; −0,032] | −0,727 [−0,865; −0,500] |

O que os números mostram:

- **A escolhida supera a atual, mas não supera o "sempre sim".** No teste, ela marcou 88 das 89 notícias como relevantes e acertou só 1 dos 25 "não". Pela condição de adoção, **não foi adotada**: o catálogo (`src/ia/catalogo.py`) não mudou e o corpus não foi reprocessado.
- **A configuração atual é a única que separa as classes.** Ela acertou 13 dos 25 "não" e tem F1 macro de 0,573, contra 0,418 do "sempre sim" e 0,454 da escolhida. Mas **não reconhece nenhuma** das 12 notícias relevantes de GD sem "solar": a probabilidade que atribui a elas vai de 0,000 a 0,487.
- **Conclusão:** nenhuma das hipóteses zero-shot testadas resolve a relevância neste corpus. A atual separa os temas, mas ignora GD sem "solar". As novas reconhecem GD sem "solar", mas não separam mais nada. A probabilidade continua visível no painel, e o filtro segue desligado por padrão.
- **Próximos passos possíveis:** testar uma hipótese de GD mais específica, avaliada num novo conjunto (este teste já foi usado); ou usar o LLM online do TP5. Em qualquer dos dois casos, a avaliação final precisa de um novo conjunto de teste, porque este já foi usado.

### 9.4 Tom

O tom foi avaliado nas notícias relevantes. A linha de base é a classe majoritária do desenvolvimento ("favorável"), e a métrica é o F1 macro das três classes.

| Conjunto | n | Favorável / neutro / desfavorável | Zero-shot: F1 macro (acurácia) | Linha de base: F1 macro (acurácia) |
|---|---|---|---|---|
| Desenvolvimento | 42 | 28 / 12 / 2 | 0,422 (0,619) | 0,267 (0,667) |
| Teste congelado | 64 | 48 / 12 / 4 | **0,248** (0,359) | **0,286** (0,750) |

O zero-shot ficou acima da linha de base no desenvolvimento, mas abaixo no teste. Com só 2 e 4 notícias desfavoráveis, a métrica oscila muito. A decisão segue o teste: **o tom continua reprovado** e permanece como tarefa experimental na API.

### 9.5 Resumo: benchmark não reexecutado

O benchmark de resumo do TP4 não foi rodado de novo. Com o corpus de 553 notícias, a mesma regra de amostragem (linha fina própria, que não repete o início do texto nem o título) daria **356 notícias**, contra as 56 da seção 4.1: ANEEL 222, MME 66, Agência Brasil 61 e Agência Gov 7. Como ANEEL, MME e Agência Gov não recebem resumo (licença CC BY-ND), um novo benchmark de resumo deveria usar só as fontes que permitem derivação.

### 9.6 Correção de métrica e segunda consulta ao teste

**Por que a métrica foi corrigida.** A primeira escolha (seção 9.2) usou o F1 da classe "sim". Neste corpus, esse é o critério errado. Todas as notícias passaram pelo filtro de palavras da coleta, 72% são relevantes, e responder sempre "sim" vence o F1-sim quase automaticamente. O critério certo é o **F1 macro**, que dá o mesmo peso à capacidade de reconhecer as notícias fora do tema.

**Nova escolha, só no desenvolvimento.** Ela usou as probabilidades já salvas (`relevancia_probabilidades_dev.csv`), sem nenhuma nova inferência. A regra foi a seguinte:

- **Restrições:** F1 macro acima do de "sempre sim" e F1 da classe "sim" maior que zero no subconjunto GD sem "solar".
- **Critério:** o maior F1 macro.
- **Empate (diferença menor que 0,005):** vence a maior precisão da classe "sim"; depois, o menor custo e o limiar mais perto de 0,5.

Desenvolvimento (59 notícias), com o melhor limiar de cada estratégia. A tabela completa está em `relevancia_desenvolvimento_v2.csv`.

| Estratégia | Limiar | F1 macro | "sim": precisão / recall | "não": precisão / recall | F1-sim em GD sem "solar" |
|---|---|---|---|---|---|
| Sempre "sim" (referência) | — | 0,416 | 0,712 / 1,000 | — / 0,000 | 0,700 |
| a) atual, limiar em uso | 0,50 | 0,695 | 0,903 / 0,667 | 0,500 / 0,824 | **0,000** (sai pela restrição) |
| a) atual | 0,30–0,40 | 0,710 | 0,906 / 0,690 | 0,519 / 0,824 | **0,000** (sai pela restrição) |
| b) ampla | 0,35 | 0,669 | 0,810 / 0,810 | 0,529 / 0,529 | 0,545 |
| c) curtas | 0,40 | 0,530 | 0,737 / 1,000 | 1,000 / 0,118 | 0,737 |
| d) híbrido, termo no texto | 0,30–0,40 | 0,687 | 0,804 / 0,881 | 0,615 / 0,471 | 0,700 |
| **d) híbrido, termo no título** | **0,30–0,40** | **0,751** | 0,892 / 0,786 | 0,591 / 0,765 | 0,667 |

**Escolha:** o híbrido com termo de GD no **título**, com limiar de **0,4**. Os limiares de 0,30 a 0,40 empataram, com a mesma precisão, e 0,4 é o mais perto de 0,5. As hipóteses curtas, escolhidas pelo critério antigo, caem para o pior F1 macro entre as estratégias: acertam só 2 dos 17 "não".

**Segunda consulta ao teste congelado.** Ela usou as probabilidades gravadas na primeira consulta (`saidas_teste_congelado.csv`), sem inferência nova. A primeira avaliação fica guardada como estava (`resultado_teste_congelado.json`), e esta está em `resultado_teste_congelado_v2.json`.

> **Esta é a SEGUNDA consulta ao teste**, feita depois de corrigir a métrica de escolha. A escolha foi refeita só no desenvolvimento e o teste não orientou nenhum ajuste. Mesmo assim, já conhecíamos o resultado da primeira consulta, inclusive o desempenho da configuração atual no teste. Por isso **a evidência é mais fraca** do que a de uma consulta única. A confirmação definitiva exige um novo conjunto de teste rotulado (seção 9.7).

F1 macro, com IC 95% por bootstrap (1.000 reamostragens) e diferenças pareadas:

| Configuração | Geral (n = 89): F1 macro [IC 95%] | "sim": precisão / recall | "não": precisão / recall | GD sem "solar" (n = 21): F1 macro [IC 95%] |
|---|---|---|---|---|
| Atual (a, 0,5) | 0,573 [0,468; 0,677] | 0,778 / 0,656 | 0,371 / 0,520 | 0,300 [0,192; 0,400] |
| **Escolhida v2 (d, título, 0,4)** | **0,678 [0,572; 0,783]** | 0,809 / 0,859 | 0,571 / 0,480 | **0,903 [0,741; 1,000]** |
| Sempre "sim" | 0,418 [0,382; 0,447] | 0,719 / 1,000 | — / 0,000 | 0,364 [0,250; 0,432] |

| Diferença pareada de F1 macro | Geral [IC 95%] | GD sem "solar" [IC 95%] |
|---|---|---|
| Escolhida v2 − atual | **+0,105 [0,028; 0,177]** | +0,603 [0,416; 0,770] |
| Escolhida v2 − sempre "sim" | **+0,259 [0,143; 0,367]** | +0,539 [0,355; 0,677] |
| Atual − sempre "sim" | +0,154 [0,039; 0,270] | −0,064 [−0,240; 0,150] |

O subconjunto GD sem "solar" está sobre-representado de propósito (seção 9.1). O ganho nele não deve ser lido como ganho no corpus inteiro.

Por fonte, F1 macro no teste:

| Fonte | n | Atual | Escolhida v2 |
|---|---|---|---|
| ANEEL | 44 | 0,455 | 0,617 |
| Agência Brasil | 27 | 0,590 | 0,590 |
| MME | 14 | 0,440 | 0,500 |
| Agência Gov | 4 | 0,333 | 0,733 |

**Decisão: adotada.** A escolhida v2 supera a atual e o "sempre sim" em F1 macro, com o IC 95% das duas diferenças acima de zero. A regra foi definida antes da consulta. O catálogo (`src/ia/catalogo.py`) passou a usar:

- **Regra:** relevante = termo de GD no título OU probabilidade da hipótese "Esta notícia trata de energia solar." de pelo menos 0,4.
- **Onde vale:** no lote, no painel e na API. Em texto livre, sem título, a regra olha a primeira linha.
- **Transparência:** a resposta informa `por_termo_gd` e o corpus guarda `relevancia_por_termo`, para mostrar quando a regra de palavra decidiu.
- **Processamento:** o corpus inteiro (553 notícias) foi reprocessado, sem resumo para as fontes do gov.br.

O ganho vem quase todo de ANEEL e Agência Gov, as fontes com GD sem "solar". Na Agência Brasil, as duas configurações dão o mesmo resultado.

**Achado: o filtro de palavras já faz a maior parte da triagem.** O filtro de relevância da coleta (`base.PADRAO_RELEVANCIA`) só deixa entrar notícias que citam solar, fotovoltaica ou termos de GD. Por isso 72% do que chega ao modelo já é relevante, e o espaço para o modelo melhorar a triagem é pequeno. O que ele acrescenta é separar as notícias que citam o tema de passagem (leilões, balanços da matriz, outras fontes).

**Achado: o NLI zero-shot superdispara com termos genéricos do setor elétrico.** Uma hipótese com termos amplos ("Esta notícia trata de geração distribuída de energia.") recebe probabilidade alta em quase qualquer notícia sobre geração de eletricidade: a mediana é **0,98 nas notícias fora do tema**. O modelo parece reconhecer o campo semântico (energia elétrica), não o conceito regulatório de GD. Por isso a regra que funcionou combina o modelo com uma palavra-chave específica no título, em vez de pôr o termo genérico dentro da hipótese.

### 9.7 Trabalho futuro

- **Novo conjunto de teste rotulado**, nunca consultado, para confirmar a configuração híbrida e servir de referência final ao TP5 (LLM online). Este teste congelado já foi consultado duas vezes.
- **Segunda rotulagem** de parte do gabarito, para medir a concordância entre pessoas.
- **GD só no corpo do texto:** o híbrido olha o título. Notícias que só tratam de GD no corpo dependem do modelo, e a variante "termo no texto" teve F1 macro menor no desenvolvimento (0,687).
