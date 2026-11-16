# Benchmark dos modelos de linguagem (TP4)

Esta pasta guarda a evidência da escolha dos modelos locais: o gabarito manual,
as saídas de cada candidato e as métricas de qualidade e custo.

| Arquivo | Conteúdo | Quem gera |
|---|---|---|
| `rotulos_benchmark.csv` | 30 notícias com relevância e tom rotulados à mão | `python -m src.ia.rotulagem` + preenchimento manual |
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

## Como rodar

```bash
python -m src.ia.benchmark --limite 3            # teste rápido (baixa os modelos)
python -m src.ia.benchmark                       # GPU, todos os candidatos
python -m src.ia.benchmark --dispositivo cpu     # mesmo teste sem GPU
python -m src.ia.benchmark --tarefa resumo --incluir-generativo
```

## Limitações conhecidas

- **Amostras pequenas.** São 30 notícias para classificação e 56 para resumo.
  Uma diferença de um ou dois pontos entre modelos está dentro do ruído; o
  benchmark serve para descartar candidatos claramente piores e para medir
  custo, não para cravar o melhor por décimos.
- **Referência do resumo.** A linha fina é um resumo humano, mas curto e
  editorial. O ROUGE mede sobreposição de palavras, não fidelidade; por isso
  os resumos também devem ser lidos em `saidas_resumo_<dispositivo>.csv`.
- **Classe rara.** Notícias desfavoráveis tendem a ser poucas. O F1 macro
  expõe o desempenho nessa classe, mas com poucos exemplos ele oscila muito.
