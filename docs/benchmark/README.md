# Benchmark dos modelos de linguagem (TP4)

Esta pasta guarda a evidência da escolha dos modelos locais: o gabarito manual,
as saídas de cada candidato e as métricas de qualidade e custo.

| Arquivo | Conteúdo | Quem gera |
|---|---|---|
| `rotulos_benchmark.csv` | 30 notícias com relevância e tom rotulados à mão | `python -m src.ia.rotulagem` + preenchimento manual |
| `rotulos_benchmark_v2_pendentes.csv` | Notícias reais ainda não rotuladas para o benchmark v2, com rótulos vazios | `python -m src.ia.rotulagem --v2` + preenchimento manual |
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
