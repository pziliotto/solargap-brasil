# Potencial solar municipal: o que explica a taxa de realização

Etapa TP4.5, Tarefa 4. Código: `src/potencial/modelo.py`. Testes: `tests/test_modelo_potencial.py`.

```
python -m src.potencial.modelo
```

O comando roda em cerca de 1 minuto, com semente fixa (`config.SEMENTE = 42`), e regera todas as saídas abaixo.

## Pergunta

A **taxa de realização** de um município é a razão entre a geração estimada da MMGD residencial e rural na própria UC (`y`) e o potencial técnico de telhados (`x`). Ela vem da Tarefa 2 e usa a visão corrigida da base ANEEL 10/2026.

A pergunta desta tarefa é: quais fatores socioeconômicos, tarifários e geográficos, **nenhum deles derivado da MMGD**, estão associados a uma taxa maior ou menor?

## Dados e premissas

| Item | Escolha |
|---|---|
| Alvo | `taxa_realizacao`, visão corrigida (`potencial_municipal.parquet`) |
| Amostra | 5.551 municípios. Saem os **19** com `flag_taxa_acima_1`: neles, a geração estimada passa do potencial, o que indica telhado médio maior que os 15 m² premissados, não adoção acima de 100%. |
| Peso amostral | Domicílios do Censo 2022, para reduzir o ruído dos municípios muito pequenos. |
| Fatores (12) | Renda domiciliar per capita média e mediana, % de população urbana, % do VAB agropecuário, tarifa B1, multi_distribuidora, cooperativa, meses de isenção do ICMS, irradiação, log da população, log da densidade e % da área agropecuária. Todos vêm de `fatores_municipais.parquet`, da Tarefa 3. |
| Fora do modelo | `icms_ano_inicio_isencao`, espelho dos meses de isenção (ρ = −0,83). `area_km2`, porque o log da área é igual ao log da população menos o log da densidade. Os dois aparecem na matriz de correlação. |
| Sem vazamento | `conferir_sem_mmgd()` barra colunas com prefixos da MMGD e do alvo (`kwp`, `potencia`, `taxa_realizacao`, `y_`, `x_`, `gap`…). Um teste cobre essa regra. |
| Ausentes | 10 municípios sem distribuidora ligada (tarifa, multi_distribuidora e cooperativa) e Fernando de Noronha sem MapBiomas. Na Ridge, a imputação pela mediana fica **dentro do pipeline** e é ajustada só no treino de cada fold. O LightGBM trata ausentes nativamente. |

A irradiação entra como fator, embora se cancele **na fórmula** da taxa (x e y usam a mesma irradiação). Aqui ela mede outra coisa: a atratividade econômica do sistema, ou seja, quanto mais sol, menor o retorno do investimento demora.

## Correlação (Spearman)

- Figura: [matriz_correlacao.png](matriz_correlacao.png)
- Valores: [matriz_correlacao.csv](matriz_correlacao.csv)

Pares com |ρ| > 0,7:

| Par | ρ |
|---|---|
| renda média × renda mediana | 0,978 |
| multi_distribuidora × cooperativa | 0,844 |
| meses de isenção do ICMS × ano de início da isenção | −0,827 (o ano ficou fora do modelo) |

Correlação mais forte de cada fator com o alvo:

| Fator | ρ com o alvo |
|---|---|
| Renda mediana | 0,67 |
| Renda média | 0,66 |
| % da área agropecuária | 0,36 |
| % do VAB agropecuário | 0,35 |
| Irradiação | −0,27 |
| Tarifa B1 | −0,09 |

## Validação cruzada

Os folds são agrupados por UF: `GroupKFold` com 5 folds externos. Nenhum município é testado com municípios da mesma UF no treino, o que evita o vazamento espacial entre vizinhos.

A busca de hiperparâmetros é **aninhada**, com `GroupKFold` de 3 folds só nas UFs de treino de cada fold externo.

| Modelo | Grade |
|---|---|
| Ridge | `alpha` ∈ {0,1; 1; 10; 100} |
| LightGBM | `num_leaves` ∈ {7, 15, 31}; `n_estimators` ∈ {300, 600}; `min_child_samples` ∈ {20, 60} |

Parâmetros fixos do LightGBM: `learning_rate` 0,03, subsample 0,8 e colsample 0,8.

Métricas fora da amostra; os valores por fold estão em [metricas_validacao_cruzada.csv](metricas_validacao_cruzada.csv). As métricas ponderadas usam o peso dos domicílios.

| Fold (UFs de teste) | Ridge R² pond. | Ridge MAE pond. | LightGBM R² pond. | LightGBM MAE pond. |
|---|---|---|---|---|
| 1 (AP, MG, RN, SE) | 0,037 | 0,066 | **0,118** | **0,059** |
| 2 (AC, MS, PA, PB, SP) | **0,465** | **0,048** | 0,405 | 0,054 |
| 3 (AL, CE, DF, PI, RJ, RS) | **0,191** | **0,049** | 0,087 | 0,051 |
| 4 (BA, ES, GO, MA, MT, RR) | 0,416 | 0,069 | **0,444** | **0,068** |
| 5 (AM, PE, PR, RO, SC, TO) | 0,252 | 0,065 | **0,432** | **0,056** |
| **Média** | 0,272 | 0,059 | **0,297** | **0,057** |
| Média sem peso (R² / MAE) | 0,246 / 0,081 | — | **0,385 / 0,071** | — |

**Modelo escolhido: LightGBM**, com `num_leaves` 7, `n_estimators` 300 e `min_child_samples` 20. Os hiperparâmetros foram escolhidos por uma busca em `GroupKFold` de 5 na amostra toda e o modelo foi reajustado com todos os dados.

Por que o LightGBM:
- tem maior R² ponderado médio fora da amostra e menor MAE;
- vence em 3 dos 5 folds pela métrica ponderada e em 4 dos 5 pela não ponderada;
- sem peso, a vantagem é grande (0,385 contra 0,246), porque o LightGBM capta não linearidades que a Ridge não capta, como a densidade e a tarifa.

A vantagem ponderada é modesta (0,025 de R²) e o desvio entre folds é alto (cerca de 0,18) nos dois modelos. O fold 3, que inclui RJ e RS, é o pior para o LightGBM.

**Leitura:** os fatores explicam cerca de 30% da variação da taxa entre municípios de UFs nunca vistas no treino. O resto fica para fatores não observados: crédito, atuação de integradores, perfil das construções, difusão entre vizinhos e a própria incerteza do potencial.

## SHAP

Para o LightGBM usamos o `TreeExplainer`. A contribuição de cada fator está na escala da taxa (0,01 = 1 ponto percentual).

| Arquivo | Conteúdo |
|---|---|
| `data/processed/shap_municipal.parquet` | Todos os 5.570 municípios: `cod_ibge`, `valor_base`, `previsao`, `shap_<fator>` (12 colunas), `alvo_observado` e `usado_no_treino` (False nos 19 excluídos) |
| `data/processed/shap_uf.parquet` | Média por UF ponderada por domicílios, só dos municípios do treino |
| [shap_importancia_global.png](shap_importancia_global.png) | Beeswarm |
| [shap_waterfall_caxias_do_sul.png](shap_waterfall_caxias_do_sul.png) | Waterfall de exemplo |

A aditividade foi verificada nos 5.570 municípios (`valor_base` + soma das contribuições = `previsao`), com erro máximo de 7×10⁻¹⁶.

**Importância global**, média de |SHAP| ponderada por domicílios:

| # | Fator | Média de \|SHAP\| | Direção |
|---|---|---|---|
| 1 | log da densidade | 0,053 | mais denso → menor taxa (mais apartamentos e menos telhado por domicílio) |
| 2 | renda média | 0,041 | mais renda → maior taxa |
| 3 | renda mediana | 0,025 | mais renda → maior taxa |
| 4 | % do VAB agropecuário | 0,016 | mais agro → maior taxa |
| 5 | tarifa B1 | 0,015 | tarifa mais alta → maior taxa |
| 6 | irradiação | 0,014 | mais sol → maior taxa |
| 7–12 | % da área agro, log da população, % urbana, ICMS, multi_distribuidora, cooperativa | < 0,006 | — |

As duas rendas juntas (0,066) são o fator mais forte. Elas dividem o crédito entre si (ver Limitações).

**Waterfall de Caxias do Sul (4305108)**:

| Fator | Valor | Contribuição |
|---|---|---|
| Valor base (média do modelo) | — | 0,1448 |
| log da densidade | 5,64 (281 hab/km²) | −0,077 |
| renda média | R$ 2.331 | +0,056 |
| renda mediana | R$ 1.667 | +0,054 |
| % do VAB agropecuário | 1,0% | −0,024 |
| log da população | 13,05 (463 mil) | −0,015 |
| % da área agropecuária | 21,5% | −0,014 |
| % de população urbana | 96,5% | −0,011 |
| irradiação | 4,37 kWh/m²/dia | −0,008 |
| tarifa B1 | R$ 735/MWh | +0,006 |
| meses de isenção do ICMS, multi_distribuidora, cooperativa | — | −0,003 no total |
| **Previsão** | — | **0,108** |
| Observado | — | 0,090 |

Caxias tem renda alta, que puxa a taxa para cima. A cidade densa, urbana e pouco agrícola, no Sul de menor irradiação, puxa mais para baixo. A previsão fica 3,7 pontos percentuais abaixo da média.

## Robustez à anomalia dos 75 kW

O modelo final, com os mesmos hiperparâmetros e a **mesma amostra** de 5.551 municípios, foi reajustado com o alvo de cada visão. Só o alvo muda. Na amostra fixa:
- a visão ANEEL tem 35 municípios com taxa > 1, todos no PR;
- a visão conservadora tem 11.

Os resultados estão em [robustez_visoes.csv](robustez_visoes.csv).

| | Corrigida | ANEEL | Conservadora |
|---|---|---|---|
| R² ponderado (CV por UF, hiperparâmetros fixos) | 0,296 | **0,165** | 0,298 |
| Top 1–4 | densidade, renda média, renda mediana, VAB agro | iguais | iguais |
| 5º fator | **tarifa** | **irradiação** | **irradiação** |
| 6º fator | irradiação | tarifa | tarifa |
| Rank do ICMS | 10º | **7º** | 10º |
| PR: taxa observada (média ponderada) | 0,107 | 0,293 | 0,141 |
| PR: previsão média | 0,109 | 0,283 | 0,138 |
| PR: SHAP médio da tarifa | −0,027 | **+0,039** | −0,017 |
| PR: SHAP médio do ICMS | −0,001 | **+0,063** | +0,007 |
| PR: SHAP médio da renda (média + mediana) | +0,076 | +0,121 | +0,090 |
| PR: SHAP médio do VAB agro | −0,013 | −0,032 | −0,019 |

**A ordem dos fatores muda.** Tarifa e irradiação trocam de lugar no 5º e 6º postos nas visões ANEEL e conservadora, e na visão ANEEL o ICMS sobe do 10º para o 7º lugar.

Os quatro primeiros fatores e as direções são estáveis. A mudança vem de o modelo **absorver a anomalia** por variáveis que funcionam como identificadores do PR:
- o ICMS é constante dentro da UF;
- a tarifa da COPEL-DIS é a mesma para quase todo o estado.

Na visão ANEEL, os +0,19 de taxa a mais no PR são atribuídos sobretudo ao ICMS (+0,063) e à tarifa (+0,039, de negativo para positivo), e o R² fora da amostra cai quase à metade. É mais uma evidência de que os 75 kW são artefato de registro e não comportamento real: os fatores socioeconômicos não explicam a taxa do PR na visão ANEEL.

A visão corrigida, padrão do projeto, não tem esse problema. A conservadora fica no meio.

## Sanidade de direção

O sinal esperado é: mais renda e tarifa mais alta → mais adoção. Ele foi conferido pela correlação de Spearman entre o valor do fator e a sua contribuição SHAP, nos municípios do treino.

| Fator | ρ(valor, SHAP) | Coef. da Ridge (padronizado) | ρ com o alvo (bruto) | Veredito |
|---|---|---|---|---|
| Renda média | +0,98 | −0,022 | +0,66 | esperado |
| Renda mediana | +0,97 | +0,070 | +0,67 | esperado |
| Tarifa B1 | +0,73 | +0,022 | **−0,09** | esperado no modelo, com ressalva |

- **Renda:** a direção é a esperada nos dois modelos. O coeficiente negativo da renda média na Ridge é efeito da colinearidade com a mediana (ρ = 0,98). A soma das duas é positiva.
- **Tarifa:** **condicionada aos demais fatores** ela vai no sentido esperado, mas a correlação bruta com o alvo é levemente negativa. As tarifas mais altas do país ficam em parte em regiões de renda mais baixa (ρ tarifa × renda média = −0,35), e o modelo separa os dois efeitos.

O efeito positivo da tarifa se concentra no topo da escala. As contribuições acima de +0,10 (de +0,15 a +0,19) são os **141 municípios da EMT (MT)**, com tarifa média de R$ 857/MWh e taxa observada média de 0,48. Ali a tarifa funciona em parte como identificador da distribuidora e do estado, com o agronegócio e a alta adoção de MT. O sinal da tarifa deve ser lido com essa ressalva; ele não foi forçado.

## Projeção 2030–2050

**É um cenário com faixa de incerteza, não uma previsão.** Os números abaixo mostram quanto a irradiação de cada município mudaria se o clima seguisse cada trajetória de emissões, na leitura de cinco modelos climáticos. Não dizem o que vai acontecer. A faixa (mínimo e máximo entre os modelos) faz parte do resultado e precisa ser lida junto com a mediana.

### Fonte

- **Base:** NASA NEX-GDDP-CMIP6 v2.0 (Thrasher et al., 2022, *Scientific Data* 9, 262, [doi:10.1038/s41597-022-01393-4](https://doi.org/10.1038/s41597-022-01393-4); dataset [doi:10.7917/OFSG3345](https://doi.org/10.7917/OFSG3345)).
- **Dados:** projeções diárias do CMIP6 com correção de viés e desagregação espacial (BCSD), em grade de 0,25°.
- **Variável:** `rsds`, a radiação de onda curta incidente na superfície, em W/m². Multiplicada por 0,024, vira kWh/m²/dia, a mesma unidade do H da NASA POWER.
- **Cenários:** SSP2-4.5 (intermediário) e SSP5-8.5 (emissões altas), contra o histórico de 1995–2014.
- **Variante:** `r1i1p1f1`.

### Modelos

Os cinco modelos foram conferidos no inventário oficial (`s3://nex-gddp-cmip6/index_v2.0_md5.txt`). Todos têm `rsds` completo em historical, ssp245 e ssp585, e aparecem como "verdes" (completos) no Apêndice I da Tech Note v2.

| Modelo | Instituição | ECS aprox. (°C) |
|---|---|---|
| GFDL-ESM4 | NOAA-GFDL (EUA) | ~2,6 |
| MPI-ESM1-2-HR | MPI-M (Alemanha) | ~3,0 |
| MRI-ESM2-0 | MRI (Japão) | ~3,1 |
| EC-Earth3 | Consórcio EC-Earth (Europa) | ~4,3 |
| ACCESS-CM2 | CSIRO-ARCCSS (Austrália) | ~4,7 |

Critérios da escolha:

1. **Instituições distintas.** Modelos da mesma família compartilham código e tenderiam a "votar" juntos na mediana.
2. **Sensibilidade climática variada.** O conjunto cobre de baixa a alta sensibilidade climática de equilíbrio (ECS). Os valores da tabela são aproximados, da literatura do CMIP6.
3. **Nenhum modelo com lacunas.** Ficaram de fora os modelos marcados como parciais na Tech Note, como GFDL-CM4, KIOST-ESM e NESM3.

### Acesso e volume

O arquivo global do S3 tem cerca de 274 MB por ano. O dado interno vem em blocos de um dia do globo inteiro, então ler só o recorte do Brasil a partir dele exigiria baixar o arquivo todo: cerca de 85 GB no total.

Por isso o coletor usa o serviço de recorte THREDDS (NCSS) da NCCS, com saída NetCDF4. O recorte vai de lat −34 a 6 e lon −74 a −34 e chega com 161 × 161 células.

Medição real da coleta (22/11/2026):

- **Volume:** 310 arquivos (5 modelos × 62 anos), 18,8 MB cada, 5,85 GB no total.
- **Tempo:** 1,9 h, com 3 requisições simultâneas.
- **Falhas:** 4 falhas transitórias (HTTP 503 e conexão encerrada), todas resolvidas na segunda tentativa.

O cache bruto fica em `data/raw/cmip6/`, ignorado no Git. Para reproduzir, rode `python -m src.data_acquisition.coletor_cmip6`; o coletor valida cada arquivo e retoma do ponto em que parou.

### Método delta

Para cada modelo, os passos são:

1. Calcular, em cada célula, a média de `rsds` em 1995–2014 (histórico) e em cada janela futura (2030–2039 e 2040–2050).
2. Calcular `delta_relativo = futuro / histórico − 1` em cada célula de 0,25°.
3. Associar cada município (ponto de `municipios_pontos.parquet`) à célula **com dado** mais próxima, por distância haversine.
   - A mediana da distância é de 10,8 km.
   - A única exceção é Fernando de Noronha (PE, 2605459), que fica a leste do recorte e foi associada a uma célula do litoral a 161 km. O delta dela deve ser lido com essa ressalva.
4. Projetar a irradiação: `H_projetada = H_observada × (1 + delta)`, em que `H_observada` é o H da NASA POWER de 2023–2025 que já está na Gold de potencial.

Só a variação relativa do modelo é usada, não o seu valor absoluto. A climatologia histórica do CMIP6 fica em média 1,9% acima do H da NASA POWER nos municípios, com 90% dos casos entre −9% e +18% e correlação de 0,56. Usar o valor absoluto do modelo misturaria essa diferença de base com a mudança climática.

O **ensemble** é a mediana, o mínimo e o máximo entre os 5 modelos:

- **Por município:** calculados direto sobre os deltas.
- **Por UF:** cada modelo é agregado primeiro (Σx projetado / Σx observado − 1) e o resumo entre modelos vem depois. Isso evita tirar a mediana de medianas.

### O que muda e o que não muda

- **x e y mudam junto com H.** São recalculados com a potência instalada fixa no valor atual, e `gap_projetado = x_projetado − y_projetado`.
- **A taxa de realização não muda com a irradiação.** Como x = kWp × H × PR × 365 / 1000 e y usa a mesma fórmula, H se cancela em y/x. O pipeline confere isso a cada execução.
- **O gap muda pouco.** Ele muda na mesma proporção do delta: no Brasil, de +0,2% a +0,6% conforme o cenário e a janela.
- **Visões.** A visão corrigida é a padrão. As colunas da visão ANEEL (`y_aneel_projetado_mwh_ano`, `gap_aneel_projetado_*`) ficam ao lado.

### Resultado por UF

A tabela mostra o delta mediano em %, com a faixa [mínimo; máximo] entre os 5 modelos.

| UF | SSP2-4.5 2030–2039 | SSP2-4.5 2040–2050 | SSP5-8.5 2030–2039 | SSP5-8.5 2040–2050 |
|---|---|---|---|---|
| AC | +1,5 [+0,1; +1,7] | +1,2 [+0,6; +1,9] | +1,6 [+0,6; +2,1] | +2,1 [+1,8; +2,4] |
| AL | −0,1 [−0,7; +0,9] | −0,4 [−1,6; +1,2] | +0,3 [−1,2; +0,9] | −0,3 [−0,8; +1,4] |
| AM | +0,0 [−0,2; +0,4] | +0,3 [−0,0; +1,0] | +0,8 [−0,0; +1,0] | +0,9 [+0,2; +1,0] |
| AP | +0,4 [−1,3; +0,8] | −0,4 [−1,5; +1,1] | +0,2 [−0,6; +0,7] | −0,4 [−1,8; +0,6] |
| BA | +1,0 [+0,4; +1,6] | +0,3 [−1,5; +1,9] | +0,9 [−0,4; +2,1] | +0,5 [+0,3; +2,2] |
| CE | −0,0 [−0,9; +1,1] | −0,4 [−0,6; +1,6] | −0,1 [−0,7; +1,5] | −0,4 [−1,0; +1,8] |
| DF | +0,9 [−0,2; +2,3] | +1,1 [−0,2; +2,4] | +1,5 [+1,2; +1,7] | +1,7 [−0,3; +2,1] |
| ES | +0,8 [+0,0; +2,0] | +0,5 [−0,4; +1,2] | +1,0 [−0,6; +1,7] | +0,6 [−0,7; +0,8] |
| GO | +0,7 [−0,3; +1,8] | +0,7 [−0,1; +2,4] | +1,2 [+1,2; +1,9] | +1,4 [−0,7; +2,2] |
| MA | −0,1 [−0,6; +0,8] | −0,3 [−0,8; +1,7] | +0,3 [+0,1; +0,7] | +0,3 [−0,9; +1,5] |
| MG | +1,2 [−0,1; +2,3] | +1,2 [−0,4; +2,2] | +1,1 [+0,9; +2,2] | +1,3 [−1,0; +1,5] |
| MS | −0,0 [−1,0; +1,3] | +0,6 [−1,1; +1,5] | +1,0 [−0,1; +1,3] | +0,2 [−1,7; +1,7] |
| MT | +1,1 [−0,2; +2,3] | +0,9 [−0,0; +3,2] | +1,5 [+0,2; +3,1] | +1,0 [−0,4; +3,7] |
| PA | +0,3 [−0,7; +0,7] | −0,3 [−0,9; +1,5] | +0,5 [+0,1; +0,7] | +0,4 [−0,8; +1,1] |
| PB | −0,1 [−1,1; +1,1] | −0,1 [−1,1; +1,4] | −0,1 [−0,8; +1,0] | −0,1 [−1,1; +1,7] |
| PE | −0,0 [−0,9; +1,1] | −0,2 [−1,3; +1,5] | +0,1 [−1,0; +1,1] | −0,2 [−0,7; +1,6] |
| PI | +0,1 [−0,4; +1,1] | +0,3 [−1,2; +2,1] | +0,6 [+0,2; +0,9] | +0,3 [−0,9; +2,3] |
| PR | −0,3 [−1,2; +0,3] | +0,0 [−0,8; +1,3] | +0,2 [−0,8; +2,1] | −0,3 [−1,8; +1,7] |
| RJ | +0,4 [−0,3; +0,9] | −0,0 [−1,1; +1,4] | +0,5 [+0,1; +0,8] | −0,3 [−1,9; +0,7] |
| RN | −0,4 [−1,1; +0,9] | −0,1 [−1,0; +1,1] | −0,3 [−0,9; +1,3] | −0,4 [−1,5; +1,4] |
| RO | +1,3 [−0,0; +1,7] | +1,0 [+0,3; +2,5] | +2,0 [+0,8; +2,7] | +2,1 [+1,2; +3,3] |
| RR | −0,1 [−0,4; +0,3] | +0,1 [−0,9; +0,7] | −0,0 [−0,6; +1,5] | +0,7 [−0,9; +1,2] |
| RS | −1,0 [−1,5; −0,0] | −0,4 [−1,4; +0,2] | −1,1 [−1,5; +1,1] | −0,8 [−2,6; +0,0] |
| SC | −0,9 [−1,4; −0,1] | −0,7 [−1,4; +0,0] | −0,9 [−1,1; +1,5] | −1,0 [−2,2; +0,5] |
| SE | +0,2 [−0,4; +1,1] | −0,5 [−1,1; +1,3] | +0,3 [−1,5; +1,3] | +0,2 [−0,9; +1,7] |
| SP | +0,4 [−0,8; +0,7] | +0,3 [−0,8; +2,4] | +1,0 [−0,2; +1,7] | +0,0 [−1,6; +1,9] |
| TO | +0,8 [−0,1; +1,7] | +0,7 [+0,0; +2,3] | +1,1 [+0,5; +1,5] | +1,5 [−0,3; +2,5] |

Leitura da tabela:

- **As variações são pequenas**, sempre abaixo de ±4% por UF. No Brasil, o potencial x sobe de 0,2% a 0,6%.
- **Há um padrão geográfico.** Os deltas tendem a ser positivos no oeste da Amazônia e no Centro-Oeste (AC, RO, MT, DF, GO) e negativos no Sul (RS, SC).
- **Na maioria das UFs, os modelos não concordam nem no sinal.** A faixa [mín; máx] cruza o zero em 16 a 24 das 27 UFs, conforme o cenário e a janela.
  - Sinal concordante nos 5 modelos em 2040–2050 só no AC e em RO, mais o TO no SSP2-4.5 e o AM e a BA no SSP5-8.5.
  - Em 2030–2039, os poucos negativos concordantes são RS e SC no SSP2-4.5.
- **A ordem de grandeza é a conclusão robusta, não o sinal em cada UF.** A mudança climática da irradiação até 2050 é pequena perto das demais incertezas do potencial, como a área de telhado (±33% entre 10 e 20 m²).

### Sanidade

- **Nenhum delta acima de ±10%.** Nenhuma combinação de município, modelo, cenário e janela passou desse limite. O maior |delta| em qualquer célula do recorte é 5,5%.
- **Deltas municipais (mediana do ensemble):** vão de −3,2% a +2,7%.
- **Extremos individuais dos modelos:** vão de −3,8% a +5,5%.
- **Conferências automáticas a cada execução:** o x recalculado bate com a Gold de potencial, e a taxa projetada é igual à atual.

### Limitações específicas

- **BCSD corrige a distribuição, não a física.** A correção de viés ajusta cada célula à climatologia observada de referência. Ela não corrige erros de nebulosidade e aerossóis dos modelos, que são as principais fontes de incerteza do `rsds` (Tech Note v2, seções 5.2 e 5.3). A NASA recomenda o produto para pesquisa e avaliação de impactos, não para decisões de projeto em locais específicos.
- **Cinco modelos são um ensemble pequeno.** A faixa mín–máx não é um intervalo de confiança, e outro conjunto de modelos poderia alargá-la.
- **Variabilidade interna.** Janelas de 10 a 11 anos ainda carregam variabilidade natural de década em década. Parte dos deltas pequenos é ruído, não sinal forçado.
- **Só a irradiação muda.** A temperatura, que reduz a eficiência dos módulos em dias quentes, e a sujidade ficam fora: o PR é fixo. A potência instalada e a área de telhado também ficam congeladas.

Para reproduzir, rode `python -m src.potencial.projecao_irradiacao`. O processamento leva cerca de 1,5 minuto com o cache local.

## Limitações

- **Associação não é causalidade.** O SHAP descreve como o modelo usa cada fator para prever, não o efeito de mudar o fator. "Mais renda → mais taxa" não quer dizer que aumentar a renda de um município elevaria a adoção na mesma medida.
- **Fatores correlacionados dividem o crédito do SHAP.** Renda média e mediana (ρ = 0,98) repartem o efeito da renda de forma arbitrária entre si. Por isso a importância das duas deve ser lida em conjunto. O mesmo vale para multi_distribuidora e cooperativa (ρ = 0,84), além de densidade, população e urbanização.
- **Variáveis constantes na UF** (ICMS) e quase constantes (tarifa, que é por distribuidora) quase não variam dentro do fold e, no modelo final, podem funcionar como identificadores de UF ou distribuidora. A validação agrupada por UF mede o desempenho sem esse atalho; a robustez mostra o seu efeito.
- **Incerteza da área de telhado.** O potencial `x` supõe 15 m² úteis por domicílio em todo o país. Onde o telhado típico é maior (casas rurais e de alto padrão) ou menor (verticalização), a taxa é sub ou superestimada. Parte do efeito da densidade pode ser esse viés de medida, e não comportamento de adoção. A Gold de potencial tem a sensibilidade de 10 e 20 m² (`x_mwh_ano_area_*`).
- **Correção dos 75 kW.** O alvo da visão corrigida usa a potência imputada dos 47.129 registros solares da COPEL-DIS (ver [atualizacao_base_10_2026.md](atualizacao_base_10_2026.md), seção 6). A imputação pode subestimar um pouco a potência real. A robustez mostra que as conclusões principais (top 4 e direções) se mantêm nas três visões.
- **Peso por domicílios.** Reduz o ruído dos municípios pequenos, mas concentra o ajuste: o tamanho amostral efetivo de Kish é de cerca de 152 municípios, e São Paulo sozinha tem 6% do peso. As métricas sem peso estão no CSV para comparação.
- **Poder explicativo moderado.** R² fora da amostra de cerca de 0,30, com variação alta entre folds (0,09 a 0,44).
- **Defasagem temporal.** O VAB agro é de 2021, o Censo de 2022 e a tarifa de 2023–2025, enquanto o alvo usa a base de 10/2026.

## Saídas

| Arquivo | Versionado |
|---|---|
| `data/processed/shap_municipal.parquet`, `data/processed/shap_uf.parquet` | sim (Gold) |
| `docs/potencial/*.png`, `*.csv` | sim |
| `data/processed/projecao_irradiacao_municipal.parquet` (5.570 municípios × 2 cenários × 2 janelas), `data/processed/projecao_irradiacao_uf.parquet` | sim (Gold) |
| `data/interim/potencial/cmip6_delta_rsds_celulas.parquet` (delta por modelo, cenário, janela e célula) | não (Silver; regerável) |
| `data/raw/cmip6/` (recortes NetCDF4 do rsds, ~5,9 GB) | não (`.gitignore`; regerável) |
| `models/modelo_taxa_realizacao.joblib` (modelo, tipo, hiperparâmetros, fatores e semente) | não (`.gitignore`; regerável) |
