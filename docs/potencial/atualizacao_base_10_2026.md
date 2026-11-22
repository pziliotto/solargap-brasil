# Atualização da base ANEEL: 08/2026 → 10/2026

**Projeto:** SolarGap Brasil · **Etapa:** TP4.5 — Potencial solar municipal
**Data:** 20/11/2026

---

## 1. O que mudou e por quê

A camada Silver (`mmgd_silver.parquet`) já estava na base ANEEL de referência **10/2026** (arquivo gerado pela ANEEL em 10/10/2026, baixado em 21/10/2026), mas a Gold versionada (`gold_mmgd_agregado.csv`, `gold_uf.csv`) ainda era da base de **08/2026** (gerada em 19/08/2026). A Tarefa 2 do TP4.5 lê a base em disco e acusou 4,82% de diferença contra a Gold. Este documento registra a unificação em 10/2026.

**Como foi feito.** A Gold foi regerada com o pipeline oficial, sem alteração de lógica:

```bash
python -m src.preparacao.construir_gold
```

Nenhum coletor foi executado. `gold_icms_uf.csv` não depende da ANEEL e não mudou. A Gold anterior continua recuperável pelo git (`git show HEAD:data/processed/gold_uf.csv`).

Em seguida, a anomalia dos 75 kW encontrada na comparação passou a ser tratada no pipeline (seção 6.3), e Silver e Gold foram regeradas com o tratamento:

```bash
python -m src.preparacao.construir_silver
python -m src.preparacao.construir_gold
python -m src.potencial.mmgd_municipal
python -m src.potencial.potencial_municipal
```

**Resumo.**

- No dado oficial, o parque solar distribuído passa de 51,3 GW para **53,8 GW** (+4,8%), com 6,5 mil empreendimentos **a menos** (−0,14%).
- A mudança não é só a inclusão de dois meses: a ANEEL alterou registros antigos. Os 73,5 mil registros do Maranhão sem fonte de geração **saíram da base**, o Amapá perdeu metade das conexões de 2025, o Amazonas dobrou as de 2019–2022, e o Paraná ganhou **2,5 GW** com apenas 1,4% mais unidades.
- O salto do Paraná vem de **47.231 registros com potência de exatamente 75 kW** (seção 6), quase todos da COPEL-DIS. A base reproduz o painel oficial da ANEEL: a inconsistência está na fonte, não no pipeline.
- **Tratamento aplicado** (seção 6.3): os 75 kW da distribuidora sinalizada por diagnóstico estatístico recebem a potência mediana de sistemas semelhantes. Na **visão corrigida**, padrão do painel, o parque é de **50,7 GW** e o CAGR 2022–2025 é de **37,7%**. No critério ANEEL, 53,8 GW e 34,6%.
- Na visão corrigida, em relação à base 08/2026, mudam de quadrante AP e MA (para "mercado emergente"), AM (para "lacuna persistente") e AC (para "líder em expansão"). O RJ continua "lacuna persistente".

> **Como ler as seções 2 a 5 e 7.** Elas comparam o **dado oficial** das duas bases (potência como publicada pela ANEEL, com os registros de fonte imputada), antes do tratamento dos 75 kW. Os números da visão corrigida estão na seção 6.3.

## 2. Totais nacionais

|Indicador|Base 08/2026|Base 10/2026|Variação|
|---|---|---|---|
|Potência solar (MW)|51.327,9|53.802,8|2.474,9 MW (+4,82%)|
|Empreendimentos solares|4.672.363|4.665.900|-6.463 (-0,14%)|
|Watts por habitante (Brasil)|252,7|264,9|+4,82%|
|Empreendimentos por 100 mil hab. (Brasil)|2.300,7|2.297,6|-0,14%|
|Registros com fonte imputada|73.501|156|−73.345|

Dado oficial, com os registros de fonte imputada. Sem eles (critério ANEEL), a base 10/2026 tem 53.788,3 MW: com apenas 156 imputados, a diferença é desprezível. Com o tratamento dos 75 kW, a visão corrigida tem 50.703,6 MW (seção 6.3).

## 3. Potência e empreendimentos por UF

Ordenado pela variação de potência.

|UF|MW 08/2026|MW 10/2026|Var. MW|Unid. 08/2026|Unid. 10/2026|Var. unid.|
|---|---|---|---|---|---|---|
|MA|1.888,6|1.108,7|-41,3%|165.020|97.458|-40,9%|
|AP|225,3|165,0|-26,8%|19.455|13.893|-28,6%|
|PB|672,6|655,4|-2,6%|57.491|56.582|-1,6%|
|AL|651,9|645,5|-1,0%|57.842|57.127|-1,2%|
|BA|2.972,2|2.962,9|-0,3%|327.544|326.636|-0,3%|
|PA|1.676,4|1.673,2|-0,2%|162.823|162.472|-0,2%|
|PI|873,0|872,7|-0,0%|90.567|90.527|-0,0%|
|PE|1.567,5|1.567,4|-0,0%|172.125|172.123|-0,0%|
|CE|1.807,4|1.807,4|-0,0%|152.694|152.693|-0,0%|
|RO|778,2|778,2|0,0%|66.759|66.759|0,0%|
|RR|121,3|121,3|0,0%|8.897|8.897|0,0%|
|RN|1.064,3|1.064,3|0,0%|124.095|124.095|0,0%|
|GO|2.414,4|2.414,9|+0,0%|186.657|186.748|+0,0%|
|AC|207,4|207,5|+0,0%|19.319|19.326|+0,0%|
|SP|7.562,1|7.568,0|+0,1%|784.355|786.089|+0,2%|
|SC|2.302,5|2.311,2|+0,4%|199.376|199.931|+0,3%|
|ES|1.361,7|1.373,1|+0,8%|109.593|111.526|+1,8%|
|MT|3.158,6|3.192,1|+1,1%|239.109|242.627|+1,5%|
|DF|580,5|589,5|+1,6%|35.928|35.994|+0,2%|
|SE|313,2|318,8|+1,8%|26.865|27.431|+2,1%|
|TO|746,3|760,9|+2,0%|65.917|67.543|+2,5%|
|RS|3.854,9|3.939,1|+2,2%|427.746|428.171|+0,1%|
|MS|1.885,9|1.928,5|+2,3%|175.131|180.409|+3,0%|
|RJ|1.946,1|2.052,7|+5,5%|199.078|204.506|+2,7%|
|MG|6.026,0|6.404,0|+6,3%|448.824|484.718|+8,0%|
|AM|327,2|454,7|+39,0%|18.071|25.944|+43,6%|
|PR|4.342,4|6.865,6|+58,1%|331.082|335.675|+1,4%|
|**Brasil**|**51.327,9**|**53.802,8**|**+4,82%**|**4.672.363**|**4.665.900**|**-0,14%**|

**Leitura.** 14 das 27 UFs mudam menos de 1%. As grandes variações não são crescimento orgânico de dois meses:

- **MA (−41%)**: a ANEEL retirou da base os registros sem fonte de geração. O MA tem agora 97.458 empreendimentos, **exatamente** o número que o painel oficial mostrava em agosto (Data Summary Report, seção 3.6). A imputação do projeto ficou sem objeto.
- **AP (−27%)**: as conexões de 2025 caíram de 8.064 para 4.232.
- **AM (+39%)**: as conexões de 2019 a 2022 praticamente dobraram (ex.: 2022, de 3.082 para 6.141).
- **PR (+58% de potência, +1,4% de unidades)**: anomalia dos 75 kW (seção 6).
- **MG (+6,3%)** e **RJ (+5,5%)**: crescimento acima do esperado para dois meses, sem padrão anômalo identificado.

## 4. Série anual e crescimento

|Ano|Conectado 08/2026 (MW)|Conectado 10/2026 (MW)|Var.|Parque 08/2026 (GW)|Parque 10/2026 (GW)|Cresc. 08/2026|Cresc. 10/2026|
|---|---|---|---|---|---|---|---|
|2016|43,9|60,5|+37,9%|0,06|0,08|—|—|
|2017|125,4|148,3|+18,3%|0,18|0,23|—|—|
|2018|419,3|440,4|+5,0%|0,60|0,67|—|—|
|2019|1.618,8|1.680,1|+3,8%|2,22|2,35|+268,5%|+252,1%|
|2020|2.980,4|3.393,4|+13,9%|5,20|5,74|+134,1%|+144,6%|
|2021|4.735,7|5.583,6|+17,9%|9,94|11,32|+91,0%|+97,3%|
|2022|8.344,1|8.880,8|+6,4%|18,28|20,20|+84,0%|+78,4%|
|2023|8.770,1|8.724,2|-0,5%|27,05|28,93|+48,0%|+43,2%|
|2024|10.788,7|10.665,8|-1,1%|37,84|39,59|+39,9%|+36,9%|
|2025|9.707,0|9.619,9|-0,9%|47,55|49,21|+25,7%|+24,3%|
|2026 (parcial)|3.780,1|4.588,5|+21,4%|51,33|53,80|—|—|

Os anos anteriores a 2023 ganharam potência, sobretudo 2020–2021 (efeito do PR). O crescimento anual continua desacelerando, mas a partir de um estoque maior: **78,4%, 43,2%, 36,9% e 24,3%** (2022 a 2025). 2026 é parcial: até outubro na base nova.

### CAGR 2022–2025 por UF

Dado oficial com imputados; a última coluna mostra o critério ANEEL (sem imputados), idêntico em todas as UFs exceto na casa decimal do Brasil. O CAGR da visão corrigida está na seção 6.3.

|UF|CAGR 08/2026|CAGR 10/2026|Diferença|CAGR 10/2026 (visão ANEEL)|
|---|---|---|---|---|
|PR|+35,4%|+18,3%|-17,1 p.p.|+18,3%|
|AM|+45,5%|+29,6%|-15,8 p.p.|+29,6%|
|AP|+105,8%|+90,9%|-14,9 p.p.|+90,9%|
|TO|+46,5%|+45,7%|-0,8 p.p.|+45,7%|
|SP|+41,9%|+41,7%|-0,2 p.p.|+41,7%|
|AL|+55,8%|+55,6%|-0,2 p.p.|+55,6%|
|PA|+47,0%|+46,9%|-0,1 p.p.|+46,9%|
|SC|+29,6%|+29,5%|-0,1 p.p.|+29,5%|
|PI|+38,7%|+38,7%|-0,0 p.p.|+38,7%|
|PE|+42,0%|+42,0%|-0,0 p.p.|+42,0%|
|CE|+45,0%|+45,0%|-0,0 p.p.|+45,0%|
|GO|+43,1%|+43,1%|-0,0 p.p.|+43,1%|
|RN|+41,4%|+41,4%|0,0 p.p.|+41,4%|
|RR|+75,6%|+75,6%|0,0 p.p.|+75,6%|
|AC|+54,7%|+54,7%|0,0 p.p.|+54,7%|
|RO|+55,2%|+55,2%|0,0 p.p.|+55,2%|
|MT|+44,0%|+44,0%|+0,0 p.p.|+44,0%|
|BA|+50,2%|+50,3%|+0,1 p.p.|+50,3%|
|SE|+40,8%|+40,9%|+0,1 p.p.|+40,9%|
|ES|+51,8%|+51,9%|+0,1 p.p.|+51,9%|
|DF|+31,8%|+32,0%|+0,2 p.p.|+32,0%|
|RS|+22,3%|+22,6%|+0,3 p.p.|+22,6%|
|MG|+27,9%|+28,8%|+0,9 p.p.|+28,8%|
|RJ|+34,2%|+35,5%|+1,3 p.p.|+35,5%|
|PB|+28,2%|+30,0%|+1,9 p.p.|+30,0%|
|MS|+40,9%|+42,8%|+1,9 p.p.|+42,8%|
|MA|+38,1%|+41,3%|+3,2 p.p.|+41,3%|
|**Brasil**|**+37,5%**|**+34,5%**|**−3,0 p.p.**|**+34,6%**|

## 5. Matriz de oportunidade

Referências nacionais no dado oficial com imputados: **252,7 → 264,9 W/hab** e **37,5% → 34,5% ao ano**. No critério ANEEL: 248,5 → 264,9 W/hab e 37,5% → 34,6%. Na visão corrigida, após o tratamento dos 75 kW: **249,7 W/hab e 37,7% ao ano** (seção 6.3).

### Estados que mudaram de quadrante

|Visão|UF|Quadrante 08/2026|Quadrante 10/2026|W/hab|CAGR 2022–2025|
|---|---|---|---|---|---|
|oficial com imputados|AP|Líder em expansão|Mercado emergente|307,1 → 224,9|+105,8% → +90,9%|
|oficial com imputados|AM|Mercado emergente|Lacuna persistente|83,0 → 115,4|+45,5% → +29,6%|
|oficial com imputados|MA|Líder em expansão|Mercado emergente|278,7 → 163,6|+38,1% → +41,3%|
|oficial com imputados|RJ|Lacuna persistente|Mercado emergente|121,2 → 127,9|+34,2% → +35,5%|
|critério ANEEL|AP|Líder em expansão|Mercado emergente|307,1 → 224,9|+105,8% → +90,9%|
|critério ANEEL|AC|Líder em expansão|Mercado emergente|249,9 → 250,0|+54,7% → +54,7%|
|critério ANEEL|AM|Mercado emergente|Lacuna persistente|83,0 → 115,4|+45,5% → +29,6%|
|critério ANEEL|MA|Lacuna persistente|Mercado emergente|154,6 → 163,6|+37,4% → +41,3%|
|critério ANEEL|RJ|Lacuna persistente|Mercado emergente|121,2 → 127,9|+34,2% → +35,5%|

### Composição dos quadrantes (dado oficial com imputados)

|Quadrante|UFs 08/2026|UFs 10/2026|
|---|---|---|
|Líder em expansão|AP, ES, GO, MA, MS, MT, PI, RN, RO, TO|ES, GO, MS, MT, PI, RN, RO, TO|
|Mercado maduro|MG, PR, RS, SC|MG, PR, RS, SC|
|Mercado emergente|AC, AL, AM, BA, CE, PA, PE, RR, SE, SP|AC, AL, AP, BA, CE, MA, PA, PE, RJ, RR, SE, SP|
|Lacuna persistente|DF, PB, RJ|AM, DF, PB|

**O que é mudança real e o que é anomalia.**

- **AP, MA e AM** mudam por alteração dos próprios registros (seção 3). O MA deixa de depender da visão escolhida: era "líder em expansão" na visão corrigida e "lacuna persistente" no critério ANEEL; agora é "mercado emergente" nas duas.
- **RJ** (nas duas visões) e **AC** (visão ANEEL) mudam porque as **referências nacionais** se moveram: o CAGR do Brasil caiu para 34,5%, abaixo dos 35,5% do RJ, e a média de W/hab subiu para 264,9, acima dos 250,0 do AC. Com o tratamento dos 75 kW (seção 6.3), as referências voltam a 249,7 W/hab e 37,7% ao ano: o RJ fica em "lacuna persistente" e o AC em "líder em expansão". **No dado oficial, a saída do RJ das lacunas persistentes é artefato da anomalia.**

## 6. Anomalia dos 75 kW

### 6.1 O padrão

Na base 10/2026, **14,1%** dos registros solares do Paraná (47.231 de 335.675) têm potência de **exatamente 75 kW**, o limite superior da microgeração. Nas demais UFs, a proporção não passa de 1,9%. São 3,54 GW, dos quais 28.149 registros (2,11 GW) na classe **Residencial**, cuja potência mediana é de 5 kW.

|Distribuidora (SigAgente)|Registros de 75 kW no PR|Potência (kW)|
|---|---|---|
|COPEL-DIS|47.076|3.530.700|
|CASTRO-DIS|44|3.300|
|CPFL JAGUARI|27|2.025|
|ESS|23|1.725|
|COCEL|22|1.650|
|CERAL-DIS|21|1.575|
|CELESC|7|525|
|PACTO ENERGIA PR|7|525|
|COSERN|3|225|
|COPREL|1|75|
|**Total**|**47.231**|**3.542.325**|

A COPEL-DIS tem 14,3% dos seus registros no PR em 75 kW. As distribuidoras com mais de mil registros no estado (ESS, CPFL Jaguari, COCEL) ficam entre 1,0% e 1,8%, proporção semelhante à das outras UFs. Proporções altas só aparecem em distribuidoras com poucos registros no PR: CASTRO-DIS e CERAL-DIS (~33%, 65 registros de 75 kW somados), COSERN e COPREL (4 registros).

Por ano de conexão, os registros de 75 kW concentram 72% a 82% da potência do PR em 2019–2021. Sem eles, a potência média residencial fica entre 4,8 e 6,8 kW em todos os anos; com eles, chega a 30–39 kW por residência em 2017–2021.

### 6.2 Validação contra o painel oficial

Consulta ao painel oficial de Geração Distribuída da ANEEL (Power BI) em **20/11/2026, 00h16**, feita pela autora. O painel indicava "Última atualização 19/11/2026 16:55" e período de conexão até 07/10/2026.

**PR, fonte solar, por ano de conexão — base (Silver, critério ANEEL) × painel:**

|Ano|kW base (Silver)|kW painel|Dif. kW|Unidades base|Unidades painel|Dif. unid.|
|---|---|---|---|---|---|---|
|2017|32.648,62|32.648,62|0,000%|814|814|0|
|2018|57.939,84|57.926,84|+0,022%|2.431|2.430|1|
|2019|315.379,89|315.372,87|+0,002%|9.746|9.744|2|
|2020|726.066,15|726.065,65|+0,000%|21.291|21.291|0|
|2021|1.358.917,59|1.358.911,79|+0,000%|36.423|36.422|1|
|2022|1.385.760,13|1.387.347,78|-0,114%|67.289|67.285|4|
|2023|762.185,32|762.179,44|+0,001%|47.204|47.203|1|
|2024|954.788,69|955.164,23|-0,039%|60.158|60.147|11|
|2025|832.906,20|833.100,26|-0,023%|61.948|61.951|-3|
|2026|411.747,41|412.742,99|-0,241%|27.772|27.901|-129|
|**2017–2026**|**6.838.339,84**|**6.841.460,47**|**-0,046%**|**335.076**|**335.188**|**-112**|

A base reproduz o painel com diferença de **0,05%** na potência e **112 unidades** no período. As diferenças se concentram em 2026, coerentes com conexões incluídas no painel depois da geração do arquivo (10/10/2026).

**PR, Residencial, 2019–2026, segundo o painel:**

|Recorte|Potência (kW)|GDs|UCs que recebem créditos|
|---|---|---|---|
|Faixa de 75 kW|2.045.925,00|27.279|34.894|
|Total residencial|3.341.937,20|231.896|341.601|

- os 75 kW são **11,8%** das GDs e **61,2%** da potência residencial;
- todos os registros da faixa têm exatamente 75,0 kW (27.279 × 75 = 2.045.925);
- a média residencial é de **14,4 kW** por GD; sem a faixa de 75 kW, cai para **6,3 kW**.

**Conferência com a Silver** (mesmo recorte: PR, Residencial, fonte solar, conexão em 2019–2026):

|Indicador|Painel|Silver|Diferença|
|---|---|---|---|
|GDs na faixa de 75 kW|27.279|27.278|−1 (um registro de 2024)|
|Potência na faixa de 75 kW (kW)|2.045.925,00|2.045.850,00|−75,00|
|GDs residenciais|231.896|231.797|−99 (−0,04%)|
|Potência residencial (kW)|3.341.937,20|3.341.284,46|−652,74 (−0,02%)|
|UCs que recebem créditos (75 kW / total)|34.894 / 341.601|34.891 / 341.494|−3 / −107|
|Participação dos 75 kW nas GDs|11,76%|11,77%|—|
|Participação dos 75 kW na potência|61,22%|61,23%|—|
|Média residencial, com / sem 75 kW (kW)|14,41 / 6,33|14,41 / 6,33|—|

A contagem anual da faixa de 75 kW também coincide: 1.977 (2019), 4.913, 10.562, 6.246, 262, 560 contra 561 no painel (2024), 929 e 1.829 (2026). No painel, a faixa é composta por 27.263 GDs da COPEL-DIS, 12 da COCEL e 3 da CPFL Jaguari, a mesma distribuição da Silver.

|Ano|2019|2020|2021|2022|2023|2024|2025|2026|Total|
|---|---|---|---|---|---|---|---|---|---|
|Base (Silver)|1.977|4.913|10.562|6.246|262|560|929|1.829|27.278|
|Painel|1.977|4.913|10.562|6.246|262|561|929|1.829|27.279|

**Divergência de transcrição.** A anotação manual registrou o total residencial como 3.341.932,20 kW; o print do painel mostra **3.341.937,20 kW**. Este relatório usa o valor do print.

**Conclusão.** A base reproduz o painel oficial; a inconsistência está na fonte oficial, não no pipeline do projeto.

**Evidências** (capturas de tela em `docs/potencial/evidencias/`):

- [`tabela_comparativa.png`](evidencias/tabela_comparativa.png) — anotação da comparação base × painel por ano e dos totais residenciais;
- [`PR_75kW_range.png`](evidencias/PR_75kW_range.png) — painel filtrado em PR, Residencial, UFV, faixa de potência 75,00–75,00 kW, conexão de 01/01/2019 a 07/10/2026;
- [`PR_full_range.png`](evidencias/PR_full_range.png) — mesmo filtro, faixa de potência completa (0 a 5.000 kW).

### 6.3 Tratamento aplicado

O pipeline trata a anomalia na camada Silver, no mesmo padrão da fonte imputada do Maranhão: **nenhum registro é excluído**, a potência oficial é preservada (`potencia_kw`) e a correção fica em colunas próprias. Código em `src/preparacao/potencia_suspeita.py`, executado pelo `construir_silver.py`; testes em `tests/test_potencia_suspeita.py`.

**1. Diagnóstico por distribuidora** (nenhuma UF ou distribuidora fixada no código; saída em `data/interim/diagnostico_potencia_suspeita.csv`):

- fração de registros com exatamente 75 kW na classe **Residencial**, onde o valor é fisicamente implausível;
- limite robusto entre as 102 distribuidoras: **mediana + 5 × MAD** = 0,1397% + 5 × 0,1397% = **0,838%**;
- sinalizada se o **limite inferior do intervalo de Wilson (95%)** da sua fração ficar acima do limite.

|Distribuidora|Residências|Com 75 kW|Fração|Wilson inferior|Sinalizada|
|---|---|---|---|---|---|
|COPEL-DIS|230.333|28.179|12,23%|12,10%|sim|
|CERAL ANITÁPOLIS|90|2|2,22%|0,61%|não|
|COPREL|834|12|1,44%|0,82%|não|
|COCEL|1.025|12|1,17%|0,67%|não|

Por que a classe Residencial e o intervalo de Wilson: a regra mediana + 5 × MAD aplicada à fração de **todas** as classes sinalizava **14 distribuidoras**, quase todas cooperativas rurais (CASTRO-DIS, CERAL-DIS, CERIPa, Ceraçá, COPREL…), onde 75 kW é porte legítimo de propriedades rurais e comércios. Restrita à classe Residencial mas sem o Wilson, sinalizava ainda 8 cooperativas com 2 a 13 registros, em que a fração é ruído amostral. Com as duas condições, só a COPEL-DIS é sinalizada. A margem para a segunda colocada é estreita (COPREL: 0,82% contra o limite de 0,84%), e a regra deve ser revista se a base mudar.

**2. Sinalização.** `flag_potencia_suspeita` em todos os registros com exatamente 75 kW da COPEL-DIS, em qualquer classe: **47.190 registros** (47.129 solares, 47.076 no PR e 53 em SC), com 3.534.675 kW oficiais nos solares.

**3. Imputação** (`potencia_corrigida_kw`). Mediana da potência dos registros **não sinalizados**, no primeiro nível com ao menos 5 registros; o nível fica em `nivel_imputacao_potencia`:

|Nível|Registros solares|%|
|---|---|---|
|município + classe + ano de conexão|41.394|87,8%|
|município + classe|5.141|10,9%|
|distribuidora + classe + ano|581|1,2%|
|UF + classe|13|0,0%|
|sem imputação|0|—|

|Classe|Registros|kW oficial|kW corrigido|Mediana imputada (kW)|
|---|---|---|---|---|
|Residencial|28.174|2.113.050|138.979|5,0|
|Rural|8.611|645.825|103.435|10,0|
|Comercial|6.689|501.675|94.804|13,0|
|Industrial|2.589|194.175|83.989|20,0|
|Demais classes|1.066|79.950|14.209|—|
|**Total**|**47.129**|**3.534.675**|**435.415**|—|

A correção reduz a potência solar em **3,10 GW**. Diferentemente da exclusão, a imputação mantém os sistemas na contagem e atribui a eles uma potência típica (435 MW).

**4. Limite conservador** (`potencia_conservadora_kw`): corrige só os **residenciais** sinalizados (28.174 registros, −1,97 GW) e mantém os 75 kW das demais classes, porque comércios, propriedades rurais e indústrias podem de fato ter 75 kW. Fica na Gold e na Tarefa 2 como valor de sensibilidade, sem seletor no painel.

**Três visões** (mesmas funções de `src/servicos/indicadores.py` usadas pelo painel e pela API):

|Indicador|Critério ANEEL|**Visão corrigida (padrão)**|Limite conservador|
|---|---|---|---|
|Potência solar Brasil (MW)|53.788,3|**50.703,6**|51.828,8|
|Potência solar PR (MW)|6.862,7|**3.769,9**|4.894,3|
|W/hab PR|599,7|**329,4**|427,7|
|CAGR 2022–2025 PR|18,3%|**35,4%**|28,4%|
|Quadrante PR|Mercado maduro|**Mercado maduro**|Mercado maduro|
|W/hab Brasil (referência)|264,9|**249,7**|255,2|
|CAGR 2022–2025 Brasil (referência)|34,6%|**37,7%**|36,9%|
|Parque 2022 / 2025 (GW)|20,20 / 49,20|**17,72 / 46,29**|18,48 / 47,37|
|Crescimento anual 2022 / 2023 / 2024 / 2025|78,4% / 43,2% / 36,9% / 24,3%|**85,4% / 48,5% / 40,0% / 25,6%**|84,1% / 47,1% / 39,1% / 25,3%|

**Quadrantes na visão corrigida:**

|Quadrante|UFs|
|---|---|
|Líder em expansão|AC, ES, GO, MS, MT, PI, RN, RO, TO|
|Mercado maduro|MG, PR, RS, SC|
|Mercado emergente|AL, AP, BA, CE, MA, PA, PE, RR, SE, SP|
|Lacuna persistente|AM, DF, PB, RJ|

Em relação ao critério ANEEL, mudam AC (mercado emergente → líder em expansão) e RJ (mercado emergente → lacuna persistente), porque as referências nacionais voltam ao patamar sem a anomalia. No limite conservador, só o RJ muda. A potência do PR na base de 08/2026 (4.342,4 MW) fica entre a visão corrigida e o limite conservador.

**Efeito na Tarefa 2 (potencial municipal).** A geração estimada `y` (Residencial + Rural, geração na própria UC) passa a usar a visão corrigida; as outras duas ficam em colunas próprias (`*_aneel`, `*_conservador`):

|Indicador|Critério ANEEL|**Visão corrigida (padrão)**|Limite conservador|
|---|---|---|---|
|kWp Residencial + Rural na própria UC (MW)|24.726,3|**22.368,8**|22.801,5|
|`y` Brasil (TWh/ano)|34,63|**31,51**|32,08|
|Taxa de realização Brasil|11,44%|**10,41%**|10,60%|
|Municípios com taxa > 1 (Brasil / PR)|54 / 35|**19 / 0**|30 / 11|

O agrupamento do Oeste do Paraná com taxa de realização acima de 1 desaparece na visão corrigida. Os 19 municípios restantes estão em MT (6), RS (4), MG (3), SP (3), GO, RO e SC (1 cada).

### 6.4 Encaminhamento

- **Tratamento aplicado** e reversível: o painel e a API mantêm o seletor "Critério ANEEL", que reproduz o dado oficial.
- A imputação provavelmente **subestima** um pouco a potência: parte dos registros comerciais, rurais e industriais da COPEL-DIS tem de fato 75 kW (nas outras distribuidoras, 1% a 2% dos registros têm esse valor). O limite conservador delimita esse efeito.
- Recomendável registrar a inconsistência junto à ANEEL (Ouvidoria ou canal do Portal de Dados Abertos), com as evidências da seção 6.2. Se a base for corrigida, o diagnóstico deixa de sinalizar a distribuidora e as visões voltam a coincidir, sem mudança de código.

## 7. Outros indicadores da Gold com variação acima de 2%

**Por UF** (W/hab, empreendimentos por 100 mil habitantes ou percentual de imputados):

|UF|W/hab 08/2026|W/hab 10/2026|Var.|Emp./100 mil 08/2026|Emp./100 mil 10/2026|Var.|% imputados|
|---|---|---|---|---|---|---|---|
|MA|278,7|163,6|-41,3%|2.435,1|1.438,1|-40,9%|44,45% → 0,00%|
|AP|307,1|224,9|-26,8%|2.651,4|1.893,4|-28,6%|—|
|PB|169,2|164,9|-2,5%|1.446,4|1.423,6|-1,6%|—|
|SE|141,7|144,2|+1,8%|1.215,6|1.241,2|+2,1%|—|
|TO|493,8|503,4|+1,9%|4.361,1|4.468,7|+2,5%|0,01% → 0,00%|
|RS|354,2|362,0|+2,2%|3.930,4|3.934,3|+0,1%|—|
|MS|684,0|699,5|+2,3%|6.352,2|6.543,6|+3,0%|—|
|RJ|121,2|127,9|+5,5%|1.240,0|1.273,8|+2,7%|—|
|MG|293,4|311,8|+6,3%|2.185,1|2.359,9|+8,0%|—|
|AM|83,0|115,4|+39,0%|458,5|658,2|+43,6%|—|
|PR|379,4|599,9|+58,1%|2.893,0|2.933,1|+1,4%|—|

**Brasil:**

- potência total +4,82%, W/hab +4,82% (252,7 → 264,9), CAGR 2022–2025 −3,0 p.p.;
- conexões por ano: 2016 a 2022 com +3,8% a +37,9%; 2026 (parcial) +21,4% por ter dois meses a mais;
- registros com fonte imputada: 73.501 → 156 (MA: 44,45% → 0%);
- `gold_mmgd_agregado.csv`: 1.863 linhas, 78,5 KB.

**Praticamente inalterados (variação ≤ 2%)**: empreendimentos por 100 mil habitantes no Brasil (−0,14%) e em 19 UFs; potência em 18 UFs. A correlação de Spearman entre o tempo de isenção de ICMS e a adoção per capita continua em **−0,06**; mudam as listas de exemplos do Data Summary Report (seção 2.5).

## 8. Validação da Tarefa 2

Com a Gold unificada, a validação do potencial municipal passou a exigir diferença menor que 1% contra a Silver **e** contra `gold_uf.csv` (`src/potencial/potencial_municipal.py`, `validar_gold`), nas duas visões com seletor:

|Visão|Tarefa 2 (kW)|Silver (kW)|`gold_uf.csv` (kW)|Diferença|
|---|---|---|---|---|
|Corrigida (`kwp_total` × `potencia_mw`)|50.703.565|50.703.565|50.703.567|0,000%|
|Critério ANEEL (`kwp_total_aneel` × `potencia_mw_aneel`)|53.788.294|53.788.294|53.788.295|0,000%|

A Tarefa 2 passou a ler a Silver (que agora tem modalidade, distribuidora e as potências tratadas) em vez de reler o ZIP da ANEEL.
