# Escolha dos modelos de linguagem — SolarGap Brasil (TP4)

**Autora:** Pâmela Lima Ziliotto
**Data:** 16/11/2026
**Evidência:** `docs/benchmark/` (rótulos, saídas de cada modelo e métricas)

---

## 1. Decisão

| Tarefa | Modelo | Situação |
|---|---|---|
| Resumo | [`recogna-nlp/ptt5-base-summ`](https://huggingface.co/recogna-nlp/ptt5-base-summ) | **Adotado** — gravado no corpus e exposto na API |
| Relevância (a notícia trata de energia solar?) | [`MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7), zero-shot | **Adotado com ressalva** — filtro do corpus, com a probabilidade sempre visível |
| Tom (favorável, desfavorável, neutro) | mesmo mDeBERTa, zero-shot | **Reprovado** — fica na API como experimental; não é gravado nem exibido como indicador |

Os dois modelos rodam localmente com Transformers/PyTorch, juntos ocupam cerca de 1,7 GB de memória de GPU e não dependem de serviço externo depois do primeiro download.

## 2. Por que modelos de tarefa e não um chatbot

O enunciado pede um modelo adequado à tarefa, considerando desempenho, custo local e acessibilidade, e cita BERT e T5 como exemplos. Para resumir e classificar notícias, modelos especializados são menores, mais rápidos e mais previsíveis. Um LLM generativo pequeno tende a acrescentar números e nomes que não estão no texto, o que é grave num projeto cujo valor está no dado validado.

Essa preferência não foi assumida: um LLM generativo (Qwen2.5-1.5B-Instruct) entrou no benchmark como candidato, e a escolha saiu da medição.

## 3. Como foi medido

**Hardware.** NVIDIA GeForce GTX 1660 Ti (6 GB), 32 GB de RAM, Windows. PyTorch 2.15 com CUDA 13.2.

**Resumo — 56 notícias.** A referência é a linha fina escrita pela redação, que funciona como um resumo humano. Para não haver vazamento, o modelo recebe título e texto **sem** a linha fina, e ficam de fora as notícias em que a "linha fina" é apenas o primeiro parágrafo repetido. A linha de base é o início do texto com o mesmo número de palavras da referência (o "lide"). Métrica: ROUGE-1 e ROUGE-L (F1), com tokenização que preserva acentos (`src/ia/metricas.py`).

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
- **A hipótese de relevância fala só em "energia solar".** No lote do corpus, o modelo julgou fora do tema notícias de geração distribuída que não usam a palavra "solar" (multa à Coelba, revisão das regras para quem gera a própria energia, impacto da geração própria nas distribuidoras). Por isso o filtro do painel vem desligado por padrão. Testar uma hipótese que inclua "geração distribuída" exige um novo conjunto rotulado, para não ajustar o modelo ao gabarito atual; fica para o TP5.

## 8. Ligação com o TP5

A relevância filtra o que o agente do TP5 vai ler, e o resumo reduz o contexto que ele precisa consumir. O tom, que os modelos locais não resolveram, é candidato natural para o LLM online permitido no TP5, avaliado contra os mesmos 30 rótulos — o que transforma este benchmark em ponto de comparação.
