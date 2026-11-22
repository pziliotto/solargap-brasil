# Benchmark dos modelos de linguagem (TP4)

Esta pasta guarda a evidência da escolha dos modelos locais: o gabarito manual,
as saídas de cada candidato e as métricas de qualidade e custo.

| Arquivo | Conteúdo | Quem gera |
|---|---|---|
| `rotulos_benchmark.csv` | 30 notícias com relevância e tom rotulados à mão | `python -m src.ia.rotulagem` + preenchimento manual |
| `rotulos_benchmark_v2_pendentes.csv` | 120 notícias do benchmark v2, rotuladas pela autora em 22/11/2026 | `python -m src.ia.rotulagem --v2` + preenchimento manual |
| `desenvolvimento_real.csv` | 59 notícias (40%) do gabarito v1 + v2, para comparar estratégias | `python -m src.ia.benchmark_relevancia dividir` |
| `teste_real_congelado.csv` | 89 notícias (60%), **congeladas** e avaliadas uma única vez | `python -m src.ia.benchmark_relevancia dividir` |
| `relevancia_probabilidades_dev.csv` | Probabilidade de cada hipótese em cada notícia do desenvolvimento | `python -m src.ia.benchmark_relevancia desenvolvimento` |
| `relevancia_desenvolvimento.csv` | Precisão, recall e F1 por estratégia, limiar e recorte (geral, fonte, GD sem "solar") | `python -m src.ia.benchmark_relevancia desenvolvimento` |
| `relevancia_escolha.json` | Estratégia escolhida, regra de escolha e condição de adoção | `python -m src.ia.benchmark_relevancia desenvolvimento` + registro da condição |
| `resultado_teste_congelado.json` | Resultado no teste, com IC por bootstrap, e o tom | `python -m src.ia.benchmark_relevancia teste` (uma vez) |
| `saidas_teste_congelado.csv` | Probabilidades e previsões de cada configuração no teste | `python -m src.ia.benchmark_relevancia teste` (uma vez) |
| `relevancia_desenvolvimento_v2.csv` | Grade do desenvolvimento por F1 macro, com precisão e recall das duas classes e F1 em GD sem "solar" | `python -m src.ia.benchmark_relevancia desenvolvimento_v2` (sem inferência) |
| `relevancia_escolha_v2.json` | Escolha pelo F1 macro, regra e condição de adoção | `python -m src.ia.benchmark_relevancia desenvolvimento_v2` |
| `resultado_teste_congelado_v2.json` | **Segunda** consulta ao teste, com IC do F1 macro por bootstrap | `python -m src.ia.benchmark_relevancia teste_v2` (uma vez, sem inferência) |
| `resultados_<dispositivo>.csv` | Uma linha por modelo e tarefa: qualidade, tempo, memória | `python -m src.ia.benchmark` |
| `saidas_resumo_<dispositivo>.csv` | Resumos de cada modelo lado a lado com a referência | `python -m src.ia.benchmark` |
| `saidas_classificacao_<dispositivo>.csv` | Previsões de cada modelo ao lado dos rótulos | `python -m src.ia.benchmark` |

## Guia de rotulagem

Leia o título, a linha fina e, se precisar, abra o link. Preencha duas colunas
e deixe a terceira para anotações.

**`relevante`** — `sim` ou `nao`

- `sim`: o assunto **principal** é energia solar (geração, mercado, regulação,
  incentivos, financiamento, tecnologia), no Brasil ou no exterior.
- `nao`: energia solar aparece de passagem, ou o assunto é outro (outras fontes
  de energia, astronomia, temas gerais de governo).

**`tom`** — preencha só quando `relevante = sim`; caso contrário, deixe vazio.

- `favoravel`: a notícia relata avanço, crescimento, incentivo, financiamento
  ou benefício para a energia solar.
- `desfavoravel`: relata obstáculo, custo, multa, corte, retrocesso
  regulatório ou risco para a energia solar.
- `neutro`: apenas informa, sem direção clara, ou traz os dois lados em
  equilíbrio.

Decida pela notícia, não pela sua opinião sobre o tema. Na dúvida entre duas
categorias, escolha a que descreve a manchete e registre a dúvida em
`observacao` — esses casos ajudam a explicar os erros dos modelos.

Acentos e maiúsculas são aceitos (`Sim`, `não`, `Favorável`): o benchmark
padroniza a leitura e recusa valores fora das categorias acima.

## Benchmark v2 (Tarefa 5a)

A planilha `rotulos_benchmark_v2_pendentes.csv` reúne notícias reais do corpus
que ainda não têm rótulo: todas as que estão fora do gabarito v1, sem filtro
de data de coleta. Ela é preenchida com o mesmo guia acima. Cada notícia traz a
palavra-chave mais específica que menciona (`palavra_chave`) e a marca
`gd_sem_solar`, que indica as notícias de geração distribuída (Lei 14.300,
fio B, micro e minigeração...) que não citam "solar" nem "fotovoltaica". É
nesse caso que a hipótese de relevância atual ("Esta notícia trata de energia
solar.") tende a falhar.

**Notícias do v1 descobertas por caminho proibido.** O gabarito v1
(`rotulos_benchmark.csv`, mantido sem alteração) contém 6 notícias da
Agência Gov descobertas pela busca interna do portal, que o `robots.txt`
proíbe (`Disallow: /*?`). O parser usado até 20/11/2026 não entendia
curingas e liberava essa busca (Data Summary Report, seção 2.3). Quatro
delas foram redescobertas pelo sitemap, um caminho permitido. As outras
**2 não voltaram** e ficam **fora do v2**:

| id | Notícia | Rótulo no v1 |
|---|---|---|
| `358fa5895453` | Chuva de meteoros Orionídeas | `nao` |
| `a2370b5d680b` | 199 anos do Observatório Nacional | `nao` |

Sem texto no corpus, essas duas também ficam sem entrada para os modelos se
o benchmark v1 for executado de novo. A lista está em
`src/ia/rotulagem.IDS_FORA_V2`.

### Divisão, desenvolvimento e teste congelado (22/11/2026)

O gabarito do benchmark v2 junta os rótulos do v1 e os da planilha v2. Saem
as 2 notícias de `IDS_FORA_V2`, e ficam 148 notícias. Elas foram divididas
uma única vez em desenvolvimento (40%) e teste (60%), com estratificação por
rótulo, fonte e `gd_sem_solar` e semente fixa (`src/ia/benchmark_relevancia.py`).

- **Teste congelado.** `teste_real_congelado.csv` não pode mudar: um teste
  automatizado confere o SHA-256 do arquivo
  (`3233b8176ad38bb377f5a2f9ac8d04379b2d1cb04fc987fc4b942627612e8577`), e a
  etapa `dividir` se recusa a regravá-lo. A etapa `teste` rodou uma vez e se
  recusa a rodar de novo enquanto existir `resultado_teste_congelado.json`.
  A etapa `teste_v2` (segunda consulta, depois da correção da métrica) tem a
  mesma trava, com `resultado_teste_congelado_v2.json`.
  Uma avaliação futura, como a do LLM do TP5, precisa de um novo conjunto de
  teste ou deve declarar que reusa este.
- **Sobre-representação proposital.** As notícias de GD sem "solar" são 23%
  do gabarito e 14% do corpus. As métricas gerais valem para este benchmark,
  não para o corpus inteiro.
- **Referência trivial.** O corpus inteiro passou pelo filtro de palavras da
  coleta, e 72% do teste é relevante. Responder sempre "sim" já dá F1 de 0,84
  na classe "sim", e toda estratégia é comparada a essa referência.

Resultado (detalhes em `docs/escolha_modelo.md`, seções 9.3 e 9.6):

- **Relevância, primeira consulta ao teste (critério F1-sim).** As três
  hipóteses curtas escolhidas no desenvolvimento superaram a hipótese atual,
  mas empataram com "sempre sim" e não foram adotadas. O critério estava
  errado: com 72% de relevantes, "sempre sim" vence o F1 da classe "sim"
  quase automaticamente. O resultado está em `resultado_teste_congelado.json`,
  que não foi alterado.
- **Relevância, segunda consulta ao teste (critério F1 macro).** A escolha
  foi refeita só no desenvolvimento, com as probabilidades salvas, e caiu no
  híbrido "termo de GD no título OU zero-shot ≥ 0,4". No teste, o F1 macro
  foi 0,678 [0,572; 0,783], contra 0,573 da atual e 0,418 do "sempre sim",
  com as duas diferenças pareadas acima de zero. A estratégia foi adotada em
  `src/ia/catalogo.py`.
- **Ressalva: a segunda consulta enfraquece a evidência.** Ela foi feita
  depois de corrigir a métrica, já com o resultado da primeira conhecido. O
  teste congelado continua com o mesmo arquivo (mesmo SHA-256), mas já foi
  consultado duas vezes. **Trabalho futuro:** um novo conjunto de teste
  rotulado, nunca consultado, para confirmar a estratégia híbrida.
- **Tom.** No teste, o zero-shot ficou abaixo da linha de base de classe
  majoritária em F1 macro e continua reprovado.
- **Resumo.** O benchmark de resumo do TP4 não foi reexecutado. Com o corpus
  de 553 notícias, a amostra seria de 356 (eram 56).

## Como rodar

```bash
python -m src.ia.benchmark --limite 3            # teste rápido (baixa os modelos)
python -m src.ia.benchmark                       # GPU, todos os candidatos
python -m src.ia.benchmark --dispositivo cpu     # mesmo teste sem GPU
python -m src.ia.benchmark --tarefa resumo --incluir-generativo
python -m src.ia.benchmark_relevancia desenvolvimento   # benchmark v2: estratégias no desenvolvimento
python -m src.ia.benchmark_relevancia teste             # já executado; recusa nova execução
python -m src.ia.benchmark_relevancia desenvolvimento_v2  # reescolha por F1 macro, sem inferência
python -m src.ia.benchmark_relevancia teste_v2          # segunda consulta; já executada, recusa nova
```

## Limitações conhecidas

- **Amostras pequenas.** No TP4 eram 30 notícias para classificação e 56 para resumo; no benchmark v2 são 59 no desenvolvimento e 89 no teste.
  Uma diferença de um ou dois pontos entre modelos está dentro do ruído; o
  benchmark serve para descartar candidatos claramente piores e para medir
  custo, não para cravar o melhor por décimos.
- **Referência do resumo.** A linha fina é um resumo humano, mas curto e
  editorial. O ROUGE mede sobreposição de palavras, não fidelidade; por isso
  os resumos também devem ser lidos em `saidas_resumo_<dispositivo>.csv`.
- **Classe rara.** Notícias desfavoráveis tendem a ser poucas. O F1 macro
  expõe o desempenho nessa classe, mas com poucos exemplos ele oscila muito.
