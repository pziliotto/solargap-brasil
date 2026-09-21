# Data Summary Report — SolarGap Brasil

**Projeto:** SolarGap Brasil — Onde está o próximo mercado solar?
**Autora:** Pâmela Lima Ziliotto **
Etapa:** TP1
**Última atualização:** 20/08/2026

---

## 1. Visão Geral

Este relatório documenta as fontes de dados utilizadas no projeto SolarGap Brasil, cujo objetivo é mapear a desigualdade regional na adoção de energia solar distribuída no Brasil, normalizada por população, alinhado aos ODS 7 (Energia Limpa e Acessível) e ODS 10 (Redução das Desigualdades).

## 2. Fontes de Dados

|Fonte|Conteúdo|Formato|Método de Obtenção|Objetivo de Uso|Estágio|
|---|---|---|---|---|---|
|**ANEEL — Relação de Empreendimentos de Geração Distribuída (MMGD)**|Registro individual de empreendimentos: potência instalada (kW), UF, município, classe de consumo, fonte de geração, modalidade, porte|ZIP (CSV interno)|Download direto do recurso CKAN|Base principal — cálculo de potência instalada agregada por estado|Em uso (TP1)|
|**ANEEL — Amostra estratificada (derivada)**|Subconjunto de até 40 registros por UF, sem colunas de identificação pessoal|CSV|Derivação local a partir do ZIP (`gerar_amostra.py`)|Versionamento no GitHub e tabela de amostra do app Streamlit|Em uso (TP1)|
|**IBGE — Censo Demográfico 2022, nível UF**|População residente por Unidade da Federação (27 registros)|JSON|API de Agregados v3 (base SIDRA), tabela 9923|Normalização per capita dos dados de MMGD|Em uso (TP1)|
|**IBGE — Censo Demográfico 2022, nível município**|População residente por município (5.570 registros)|JSON|API de Agregados v3 (base SIDRA), tabela 9923|Normalização per capita em granularidade municipal (análise complementar)|Em uso (TP1)|
|Notícias e portais sobre incentivos estaduais à energia solar|Texto|HTML → CSV/TXT|Web scraping (BeautifulSoup)|Contexto qualitativo por estado; insumo para nuvem de palavras|Planejado (TP2)|
|Portais dinâmicos de secretarias estaduais (ICMS sobre GD)|Texto / tabelas|HTML renderizado via JavaScript|Web scraping dinâmico (Selenium)|Enriquecer a análise de disparidade com dado de política pública|Planejado (TP3)|

### 2.1 Parâmetros das consultas ao IBGE

- **Tabela:** 9923 — População residente, por situação do domicílio (Censo Demográfico 2022)
- **Variável:** 93 — População residente (unidade: Pessoas)
- **Classificação:** 1 (Situação do domicílio), categoria 6795 — Total
- **Níveis territoriais:** N3 (Unidade da Federação) e N6 (Município)
- **Período:** 2022 — único período disponível nesta tabela

### 2.2 Colunas da base ANEEL utilizadas nos KPIs

|Coluna|Papel no projeto|Observação|
|---|---|---|
|`SigUF`|Chave de agregação regional|Sigla da UF|
|`MdaPotenciaInstaladaKW`|Numerador dos KPIs de potência|Valor em **kW**; conversão para MW na camada Silver|
|`DscFonteGeracao`|Filtro da fonte solar|A base inclui também hídrica, eólica, térmica e biogás. Vazio em 73.501 registros (99,8% no MA); **ver seção 3.4**|
|`CodUFibge`|Chave de junção com o IBGE|Tipo `float64` na origem; requer conversão explícita antes do merge|
|`CodMunicipioIbge`|Chave de junção municipal|Código IBGE de 7 dígitos|
|`DscClasseConsumo`|Segmentação por perfil de consumidor|Análise complementar|
|`DthAtualizaCadastralEmpreend`|Eixo temporal — data de conexão|Validado contra o painel oficial da ANEEL; **ver seção 3.1**|
|`SigTipoGeracao`|Verificação da fonte de geração|Sigla do tipo de usina (UFV, UTE, EOL, CGH). Correspondência de 100% entre `UFV` e "Radiação solar"; vazio nos mesmos registros em que `DscFonteGeracao` é vazio|

## 3. Observações sobre Qualidade e Tratamento

- Os dados brutos (ANEEL, IBGE) são armazenados sem alteração em `data/raw/` (camada Bronze) e nunca editados diretamente.
- A limpeza, tipagem, correção e aplicação dos critérios de exclusão ocorre em `data/interim/` (camada Silver), pelo script `src/preparacao/construir_silver.py`. A base é lida e gravada em blocos de 500 mil registros, sem carregar o arquivo completo em memória.
- O dado final, agregado e normalizado por população, fica em `data/processed/` (camada Gold), pelo script `src/preparacao/construir_gold.py`, e alimenta a aplicação.
- A granularidade da ANEEL (registro individual de empreendimento) difere da granularidade do IBGE (população agregada por UF ou município) — a agregação é necessária antes do merge.
- Em leitura por chunks, as colunas são carregadas como texto (`dtype=str`) para evitar inferência de tipo divergente entre blocos. A tipagem é responsabilidade da camada Silver.

### 3.1 Natureza temporal da base e validação do campo de data

O campo `AnmPeriodoReferencia` apresenta **um único valor (08/2026)** em todos os registros, indicando que o arquivo é um **retrato da situação corrente** — a relação dos empreendimentos ativos no momento da geração do conjunto de dados — e não uma série histórica de snapshots mensais acumulados.

Em consequência, o único campo temporal disponível para a análise de série histórica é `DthAtualizaCadastralEmpreend`. A nomenclatura do campo sugere tratar-se de data de atualização cadastral, o que levantou a hipótese de que o campo não seria adequado como proxy de adoção — registros atualizados em lote (como na migração do sistema SISGD para o sistema MMGD) poderiam concentrar artificialmente contagens em períodos específicos.

**Validação realizada.** A hipótese foi testada por cruzamento com o painel oficial de Geração Distribuída da ANEEL, disponível em:

> https://app.powerbi.com/view?r=eyJrIjoiY2VmMmUwN2QtYWFiOS00ZDE3LWI3NDMtZDk0NGI4MGU2NTkxIiwidCI6IjQwZDZmOWI4LWVjYTctNDZhMi05MmQ0LWVhNGU5YzAxNzBlMSIsImMiOjR9

Constatou-se que a própria ANEEL utiliza esse campo como **"Ano de conexão"** no painel, e que a distribuição anual de registros obtida localmente **reproduz exatamente** os valores publicados no painel oficial.

**Conclusão.** O campo é adotado como referência temporal de conexão, seguindo a interpretação da própria fonte. A nomenclatura da coluna é enganosa em relação ao seu conteúdo semântico; a evidência do painel oficial prevalece. O cruzamento valida simultaneamente a interpretação do campo e a correção do pipeline de leitura, parsing e agregação implementado no projeto.

**Distribuição anual observada** (`DthAtualizaCadastralEmpreend`, 4.673.268 registros, nenhuma data inválida):

|Ano|Registros|Ano|Registros|
|---|---|---|---|
|1900|15|2019|124.714|
|2009|23|2020|228.017|
|2010|5|2021|460.173|
|2011|40|2022|816.548|
|2012|37|2023|705.437|
|2013|78|2024|931.223|
|2014|273|2025|925.632|
|2015|1.296|2026|424.428|
|2016|6.269|||
|2017|13.280|||
|2018|35.780|||

A retração observada em 2023 frente a 2022 é consistente com o contexto regulatório descrito no Project Charter: a antecipação de conexões até janeiro de 2023, motivada pela isenção dos custos do Fio B, seguida de arrefecimento e posterior retomada.

### 3.2 Critérios de exclusão de registros

Os seguintes registros são descartados na camada Silver, com o respectivo critério:

|Critério|Registros|Justificativa|
|---|---|---|
|Ano = 1900|15|Data-sentinela; valor de preenchimento sem significado real|
|Ano < 2012|68|A REN nº 482/2012 instituiu o marco regulatório da MMGD; registros anteriores são anomalias cadastrais|
|Potência nula ou ≤ 0|41|Fisicamente inválido para uma usina conectada. Todos os casos no PR, fonte solar, entre 2020 e 2025|

**Tratamento do ano corrente (2026):** os dados cobrem apenas parte do ano (referência 08/2026). Comparações diretas com anos completos são inválidas. Nas visualizações, 2026 é sinalizado como período parcial ou excluído das séries de crescimento anual.

**Balanço:** 4.673.268 registros lidos, 124 descartados, 4.673.144 mantidos na Silver. A conciliação (mantidos + descartados = lidos) é verificada automaticamente a cada execução.

### 3.3 Nota de atualização da fonte

A ANEEL suspendeu temporariamente a atualização dos dados de conexões de MMGD entre 23/09/2025 e 24/10/2025, em razão da migração do sistema SISGD para o novo sistema MMGD. Conexões desse período podem ter sido inseridas retroativamente.

### 3.4 Correções aplicadas na camada Silver

As correções abaixo foram identificadas pelo script `src/preparacao/diagnostico_silver.py`, que investigou os alertas de monitoramento emitidos na primeira execução da camada Silver.

#### 3.4.1 Fonte de geração ausente — imputação como solar

**Achado.** 73.501 registros chegam sem `DscFonteGeracao` e sem `SigTipoGeracao`. A concentração é quase total em uma unidade da federação: 73.352 (99,8%) no Maranhão. O padrão indica falha de preenchimento de uma distribuidora, e não usinas de outra fonte. Não há outro campo da base que permita recuperar a fonte.

**Evidência para a imputação.**

- Entre os 4.599.684 registros com fonte conhecida, 4.598.903 são "Radiação solar" — **99,98%**.
- A distribuição de potência do grupo sem fonte é praticamente idêntica à dos solares:

|Potência (kW)|Sem fonte|Radiação solar|
|---|---|---|
|Média|11,64|10,97|
|1º quartil|5,00|4,00|
|Mediana|6,00|5,85|
|3º quartil|10,00|8,20|

- 79,9% dos registros sem fonte são da classe residencial, perfil típico da geração solar em telhado.
- A distribuição temporal (2018 a 2026) acompanha a curva de crescimento da geração solar distribuída.

**Decisão.** Os registros são imputados como "Radiação solar". Se a proporção geral de fontes se repetir nesse grupo, o erro esperado é de aproximadamente 12 registros em 73.501. A alternativa — excluí-los — garantiria um erro de 73.501 registros concentrado em um único estado.

**Rastreabilidade.** A coluna booleana `fonte_imputada` marca cada registro corrigido e segue até a camada Gold. A decisão é reversível e o painel permite ao usuário alternar entre as duas visões (ver seção 3.6).

**Impacto.** A imputação eleva o Maranhão de 91.668 para 165.020 empreendimentos solares (+80%), com efeito direto sobre a posição do estado nos indicadores per capita.

#### 3.4.2 Código municipal incompleto e UF ausente

Um registro chega sem `SigUF` e com código municipal de 6 dígitos (`431780`), quando o padrão do IBGE é de 7. O código de 7 dígitos é o de 6 acrescido de um dígito verificador; a correspondência é recuperada pela tabela municipal do IBGE. A UF é derivada do prefixo do código municipal (43 — Rio Grande do Sul).

Os demais 4.673.143 registros têm código municipal de 7 dígitos, com prefixo coerente com o código da UF em 100% dos casos.

### 3.5 Camada Gold

|Tabela|Grão|Conteúdo|Tamanho|
|---|---|---|---|
|`gold_mmgd_agregado.csv`|UF × ano × classe de consumo × fonte imputada|Potência (kW), quantidade de empreendimentos, indicador de ano parcial|81KB|
|`gold_uf.csv`|UF|Nome, região, população (Censo 2022), potência (MW), watts por habitante, empreendimentos por 100 mil hab., % de registros imputados|2KB|

**Por que uma tabela no menor grão.** O painel filtra por período, classe de consumo e inclusão de registros imputados. Uma tabela já totalizada por UF impediria recalcular esses recortes. A tabela agregada guarda o menor nível que o painel precisa e a aplicação soma depois de filtrar. O mesmo vale para a potência acumulada, calculada na aplicação.

**Métricas per capita.** Watts por habitante é a métrica principal: ordem de grandeza legível e unidade usual no setor. Empreendimentos por 100 mil habitantes a complementa — potência mede volume investido, contagem mede difusão.

**Escopo.** Apenas fonte solar, incluindo os registros imputados, marcados pela coluna `fonte_imputada`.

### 3.6 Validação contra o painel oficial da ANEEL

O resultado da camada Gold foi comparado com o painel oficial de Geração Distribuída da ANEEL (dados até 31/08/2026). O arquivo processado foi gerado pela ANEEL em 19 de Agosto de 2026.

Como o painel não contabiliza os registros sem fonte, a comparação é feita em duas visões:

|Métrica|Painel ANEEL|Projeto — critério ANEEL (sem imputados)|Projeto — com correção de preenchimento|
|---|---|---|---|
|Empreendimentos solares (Brasil)|4.655.916|4.598.862|4.672.363|
|Potência solar (MW)|53.650,9|50.472,3|51.327,9|
|Empreendimentos solares (MA)|97.458|91.668|165.020|

**Contagem.** No critério ANEEL, a diferença é de 1,2%. O arquivo processado foi gerado em 19/08/2026 e o painel reflete dados até 31/08/2026; no ritmo de conexões de 2025, os 12 dias de defasagem respondem por cerca de metade da diferença. O restante é compatível com as inserções retroativas decorrentes da migração de sistema (seção 3.3). A contagem valida o pipeline de leitura, correção e agregação.

**Maranhão.** O número do painel é próximo ao do projeto **sem** imputados. O painel, portanto, filtra pelo mesmo campo vazio e deixa de fora os registros sem rótulo. Isso não constitui evidência de que esses registros sejam de outra fonte — apenas de que não foram contabilizados. **Conclusão: o painel oficial provavelmente subestima o Maranhão em cerca de 73 mil sistemas solares**, por falha de preenchimento cadastral.

Por esse motivo, o dashboard oferece as duas visões: "Critério ANEEL", que reproduz os números oficiais, e "Com correção de preenchimento", adotada como padrão e acompanhada de nota explicativa.

**Potência — divergência em aberto.** No critério ANEEL, a potência do painel é 6,3% superior à do projeto, desproporcional à diferença de contagem (1,2%) e não explicável pela defasagem de 12 dias entre as extrações. A hipótese de inclusão de outras fontes no indicador do painel foi testada e descartada: as demais fontes somam apenas 301,7 MW. As hipóteses remanescentes são a diferença de data de extração e diferenças de metodologia de cálculo no painel. A divergência permanece registrada como pendência.

### 3.7 Pendências

|Item|Situação|
|---|---|
|Classe de consumo `REBR`|39.946 registros em 14 UFs, sem significado documentado. Mantida sem alteração até consulta ao dicionário de dados da ANEEL|
|Divergência de potência com o painel oficial|Ver seção 3.6|

## 4. Governança e Privacidade

A base original da ANEEL contém duas colunas com dado pessoal identificável: `NumCPFCNPJ` e `NomTitularEmpreendimento`.

Como o repositório do projeto é público e nenhum indicador do SolarGap Brasil depende da identificação do titular, essas colunas são **excluídas na leitura** (parâmetro `usecols` do pandas), e não removidas após o carregamento. A distinção é relevante: o dado sensível nunca é carregado em memória nem gravado em disco pelos artefatos do projeto, em conformidade com o princípio de minimização de dados.

O mesmo filtro é aplicado na geração da amostra versionada e será mantido em todos os tratamentos das camadas Silver e Gold.

## 5. Versionamento e Reprodutibilidade

|Artefato|Tamanho|Versionado no Git|Justificativa|
|---|---|---|---|
|ANEEL — ZIP completo|~105 MiB (CSV interno ~1,4 GB)|❌ Não|Excede o limite de 100 MB por arquivo do GitHub|
|ANEEL — amostra estratificada|< 1 MB|✅ Sim|Permite executar o app demo sem download da base completa|
|IBGE — UF|~0,01 MB|✅ Sim|Volume irrelevante|
|IBGE — municípios|~1,9 MB|✅ Sim|Volume aceitável|
|`data/interim/` (Silver)|—|❌ Não|Sempre reproduzível a partir da camada Bronze|
|`gold_mmgd_agregado.csv` (Gold)|81KB|✅ Sim|Alimenta o dashboard; permite todos os filtros sem a base completa|
|`gold_uf.csv` (Gold)|2KB|✅ Sim|Indicadores por UF; base da visão padrão do painel e da futura API (TP3)|

**Regeneração da base completa:** `python -m src.data_acquisition.aneel` a partir da raiz do projeto.

⚠️ **Restrição de acesso:** o portal de dados abertos da ANEEL aplica filtragem geográfica de IP. A execução do coletor a partir de fora do território brasileiro falha; é necessária VPN com saída no Brasil. Esta restrição não afeta a avaliação do projeto, uma vez que a amostra e a camada Gold estão versionadas.

**Amostragem estratificada:** a amostra não corresponde às primeiras N linhas do arquivo. Como a base vem ordenada por distribuidora e período, um recorte sequencial poderia conter poucos estados — inadequado para um projeto cujo objeto é a disparidade entre unidades da federação. A amostra contém até 40 registros de cada UF.

## 6. Licenciamento e Uso

**ANEEL — Relação de Empreendimentos de Geração Distribuída (MMGD):**

> This _Relação de Empreendimentos de Geração Distribuída_ is made available under the Open Database License: http://opendatacommons.org/licenses/odbl/1.0/. Any rights in individual contents of the database are licensed under the Database Contents License: http://opendatacommons.org/licenses/dbcl/1.0/

A licença ODbL exige atribuição da fonte e possui cláusula _share-alike_: bases derivadas distribuídas publicamente — incluindo os arquivos das camadas Silver e Gold deste projeto — permanecem sob os mesmos termos.

**IBGE — Censo Demográfico 2022:** dados públicos disponibilizados pelo Instituto Brasileiro de Geografia e Estatística para uso livre, incluindo fins acadêmicos e de pesquisa, mediante citação da fonte.

**Dados obtidos via scraping (TP2/TP3):** provenientes de páginas públicas de órgãos governamentais, respeitando os termos de uso e o `robots.txt` de cada portal.

## 7. Próximos Passos

- **TP2:** incorporar fontes textuais via scraping estático (BeautifulSoup); consolidar a camada Silver e publicar a camada Gold
- **TP3:** incorporar fontes dinâmicas via Selenium; expor os dados processados por meio de API própria (FastAPI)
- **TP4:** processar o corpus textual coletado com modelo de linguagem local (HuggingFace/Transformers)
- **TP5:** integrar agente inteligente de recomendação ao dashboard final
