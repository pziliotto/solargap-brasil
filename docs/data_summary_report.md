# Data Summary Report — SolarGap Brasil

**Projeto:** SolarGap Brasil — Onde está o próximo mercado solar?
**Autora:** Pâmela Lima Ziliotto
**Etapa:** TP2
**Última atualização:** 22/09/2026

---

## 1. Visão Geral

Este relatório documenta as fontes de dados utilizadas no projeto SolarGap Brasil, cujo objetivo é mapear a desigualdade regional na adoção de energia solar distribuída no Brasil, normalizada por população, alinhado aos ODS 7 (Energia Limpa e Acessível) e ODS 10 (Redução das Desigualdades).

## 2. Fontes de Dados

|Fonte|Conteúdo|Formato|Método de Obtenção|Objetivo de Uso|Estágio|
|---|---|---|---|---|---|
|**ANEEL — Relação de Empreendimentos de Geração Distribuída (MMGD)**|Registro individual de empreendimentos: potência instalada (kW), UF, município, classe de consumo, fonte de geração, modalidade, porte|ZIP (CSV interno)|Download direto do recurso CKAN|Base principal — cálculo de potência instalada agregada por estado|Em uso (TP1–TP2)|
|**ANEEL — Amostra estratificada (derivada)**|Subconjunto de até 40 registros por UF, sem colunas de identificação pessoal|CSV|Derivação local a partir do ZIP (`gerar_amostra.py`)|Referência versionada da estrutura original da base; usada na demo do TP1|Em uso (TP1)|
|**IBGE — Censo Demográfico 2022, nível UF**|População residente por Unidade da Federação (27 registros)|JSON|API de Agregados v3 (base SIDRA), tabela 9923|Normalização per capita dos dados de MMGD|Em uso (TP1–TP2)|
|**IBGE — Censo Demográfico 2022, nível município**|População residente por município (5.570 registros)|JSON|API de Agregados v3 (base SIDRA), tabela 9923|Normalização per capita em granularidade municipal (análise complementar)|Em uso (TP1)|
|**Agência Brasil (EBC) — notícias sobre energia solar e geração distribuída**|Texto integral, título, linha fina, data de publicação, URL (114 notícias, 2014–2026)|HTML → CSV|Web scraping estático (BeautifulSoup) de páginas de tag|Nuvem de palavras, estatísticas de texto e contexto qualitativo por UF; corpus para LLM no TP4|Em uso (TP2)|
|CONFAZ — adesão estadual ao Convênio ICMS 16/2015|Situação e data de adesão por UF|HTML → CSV|Web scraping (BeautifulSoup; Selenium se a página exigir)|Variável de política pública para a análise de disparidade|Planejado (TP3)|

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
|`MdaPotenciaInstaladaKW`|Numerador dos KPIs de potência|Valor em **kW**; conversão para MW na camada Gold|
|`DscFonteGeracao`|Filtro da fonte solar|A base inclui também hídrica, eólica, térmica e biogás. Vazio em 73.501 registros (99,8% no MA); **ver seção 3.4**|
|`CodUFibge`|Chave de junção com o IBGE|Tipo `float64` na origem; requer conversão explícita antes do merge|
|`CodMunicipioIbge`|Chave de junção municipal|Código IBGE de 7 dígitos|
|`DscClasseConsumo`|Segmentação por perfil de consumidor|Análise complementar|
|`DthAtualizaCadastralEmpreend`|Eixo temporal — data de conexão|Validado contra o painel oficial da ANEEL; **ver seção 3.1**|
|`SigTipoGeracao`|Verificação da fonte de geração|Sigla do tipo de usina (UFV, UTE, EOL, CGH). Correspondência de 100% entre `UFV` e "Radiação solar"; vazio nos mesmos registros em que `DscFonteGeracao` é vazio|

### 2.3 Corpus de notícias (web scraping)

**Script:** `src/data_acquisition/noticias.py` · **Saída:** `data/processed/corpus_noticias.csv`

**Fonte e método.** Páginas de tag da Agência Brasil (`energia-solar-1`, `energia-solar`, `geracao-distribuida`, `energia-renovavel`, `energias-renovaveis`), em HTML estático com paginação `?page=N`. O script percorre as páginas de cada tag até não encontrar links novos e, em seguida, baixa cada notícia.

**Extração independente do layout.** O script não depende de classes CSS do site, que mudam com frequência:

- links de notícia identificados pelo padrão de URL `/<editoria>/noticia/AAAA-MM/<slug>`;
- data extraída do texto "Publicado em DD/MM/AAAA - HH:MM";
- título e linha fina lidos das meta tags `og:title` e `og:description`;
- corpo definido como o elemento cujos parágrafos `<p>` somam o maior volume de texto, após a remoção de menus, cabeçalho e rodapé.

**Boas práticas de coleta.** Consulta ao `robots.txt` antes de cada requisição, `User-Agent` identificado como projeto acadêmico, pausa de 1,5 segundo entre requisições e *retry* com espera exponencial (reaproveitando `calcular_espera_backoff` do `coletor_base.py`). O HTML bruto é salvo em `data/raw/html/agenciabrasil/` (camada Bronze, não versionada): uma notícia já baixada nunca é requisitada de novo.

**Resultado da coleta (21/09/2026).**

|Etapa|Notícias|
|---|---|
|Links distintos encontrados nas tags|126|
|Falhas de download / bloqueio por `robots.txt`|0|
|Descartadas por irrelevância (sem menção a solar, fotovoltaica ou geração distribuída)|12|
|**Notícias no corpus**|**114**|

Período coberto: 27/06/2014 a 08/07/2026. Tamanho médio: 3.019 caracteres. Todas as notícias com data identificada. UFs mais mencionadas: SP (20), RJ (16), MG (12), BA (11) e PR (10).

**Esquema do corpus.**

|Coluna|Conteúdo|
|---|---|
|`id`|Hash da URL (12 caracteres)|
|`fonte`, `url`, `tag_origem`|Origem e rastreabilidade de cada registro|
|`data_publicacao`, `coletado_em`|Data da notícia e data da coleta|
|`titulo`, `linha_fina`, `texto`|Conteúdo textual integral|
|`ufs_mencionadas`|Siglas das UFs cujo nome aparece no texto, detectadas por expressão regular com fronteira de palavra ("Mato Grosso" não é confundido com "Mato Grosso do Sul")|
|`nivel_texto`|`integral` — reservado para fontes futuras que admitam apenas metadados|
|`resumo`, `sentimento`|Vazias no TP2; serão preenchidas pelo modelo de linguagem local no TP4, sem alteração de esquema|

**Observação analítica.** A cobertura da imprensa se concentra nos estados do Sudeste, o que não coincide necessariamente com o ranking de adoção per capita. O dashboard exibe as duas informações lado a lado para permitir a comparação.

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

**Tratamento do ano corrente (2026):** os dados cobrem apenas parte do ano (referência 08/2026). Comparações diretas com anos completos são inválidas. No dashboard, 2026 é sinalizado como período parcial: faixa sombreada no gráfico de evolução e aviso na barra lateral sempre que o ano está dentro do filtro. A coluna `ano_parcial` da camada Gold carrega essa marcação como dado.

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

### 3.8 Uso dos dados na aplicação

O dashboard (`src/app/demo_app.py`) lê exclusivamente a camada Gold, o que permite executá-lo sem a base completa da ANEEL.

|Aba|Dados utilizados|O que o usuário faz|
|---|---|---|
|Panorama|`gold_mmgd_agregado.csv`, `gold_uf.csv`|Ranking das 27 UFs na métrica escolhida, média nacional como referência, destaque e posição de uma UF|
|Evolução|`gold_mmgd_agregado.csv`|Série anual ou acumulada por UF, em potência ou número de empreendimentos|
|Notícias|`corpus_noticias.csv`|Nuvem de palavras, termos mais frequentes, notícias por ano, UFs mais mencionadas e tabela com links, filtráveis por UF|
|Dados|Todas as anteriores + arquivo do usuário|Download dos recortes filtrados; upload de um indicador próprio por UF para comparação com a adoção|

**Filtros globais.** Visão dos dados ("Com correção de preenchimento" ou "Critério ANEEL", seção 3.6), métrica, período de conexão e classe de consumo. Os indicadores per capita são recalculados após os filtros, a partir do grão da Gold.

**Cache.** As funções de leitura, as agregações filtradas, a contagem de termos e a geração da nuvem de palavras usam `st.cache_data` (`src/app/carregamento.py`): cada combinação de parâmetros é calculada uma única vez por sessão do servidor.

**Estado de sessão.** Os filtros e a UF em destaque persistem entre abas e interações. O arquivo enviado pelo usuário é validado uma única vez e mantido em `st.session_state` até ser removido.

**Upload.** O usuário baixa um CSV-modelo com as 27 UFs, preenche uma coluna de valor e envia o arquivo. A validação (`src/app/validacao_upload.py`) verifica a coluna `sigla_uf`, siglas válidas, duplicidades e valores numéricos (aceitando decimal com vírgula ou ponto), com mensagens de erro específicas.

## 4. Governança e Privacidade

A base original da ANEEL contém duas colunas com dado pessoal identificável: `NumCPFCNPJ` e `NomTitularEmpreendimento`.

Como o repositório do projeto é público e nenhum indicador do SolarGap Brasil depende da identificação do titular, essas colunas são **excluídas na leitura** (parâmetro `usecols` do pandas), e não removidas após o carregamento. A distinção é relevante: o dado sensível nunca é carregado em memória nem gravado em disco pelos artefatos do projeto, em conformidade com o princípio de minimização de dados.

O mesmo filtro é aplicado na geração da amostra versionada e em todos os tratamentos das camadas Silver e Gold.

**Arquivos enviados pelo usuário.** O conteúdo enviado pelo serviço de upload permanece apenas na sessão do navegador (`st.session_state`) e não é gravado em disco nem versionado.

## 5. Versionamento e Reprodutibilidade

|Artefato|Tamanho|Versionado no Git|Justificativa|
|---|---|---|---|
|ANEEL — ZIP completo|~105 MiB (CSV interno ~1,4 GB)|❌ Não|Excede o limite de 100 MB por arquivo do GitHub|
|ANEEL — amostra estratificada|< 1 MB|✅ Sim|Referência da estrutura original da base, sem dados pessoais|
|IBGE — UF|~0,01 MB|✅ Sim|Volume irrelevante|
|IBGE — municípios|~1,9 MB|✅ Sim|Volume aceitável|
|`data/interim/` (Silver)|—|❌ Não|Sempre reproduzível a partir da camada Bronze|
|`gold_mmgd_agregado.csv` (Gold)|81KB|✅ Sim|Alimenta o dashboard; permite todos os filtros sem a base completa|
|`gold_uf.csv` (Gold)|2KB|✅ Sim|Indicadores por UF; base da visão padrão do painel e da futura API (TP3)|
|`corpus_noticias.csv`|< 1 MB|✅ Sim|Alimenta a aba Notícias; corpus para o modelo de linguagem no TP4|
|`data/raw/html/` (cache do scraping)|—|❌ Não|Reproduzível executando `python -m src.data_acquisition.noticias`|

**Regeneração da base completa:** `python -m src.data_acquisition.aneel` a partir da raiz do projeto.

⚠️ **Restrição de acesso:** o portal de dados abertos da ANEEL aplica filtragem geográfica de IP. A execução do coletor a partir de fora do território brasileiro falha; é necessária VPN com saída no Brasil. Esta restrição não afeta a avaliação do projeto, uma vez que a amostra e a camada Gold estão versionadas.

**Amostragem estratificada:** a amostra não corresponde às primeiras N linhas do arquivo. Como a base vem ordenada por distribuidora e período, um recorte sequencial poderia conter poucos estados — inadequado para um projeto cujo objeto é a disparidade entre unidades da federação. A amostra contém até 40 registros de cada UF.

## 6. Licenciamento e Uso

**ANEEL — Relação de Empreendimentos de Geração Distribuída (MMGD):**

> This _Relação de Empreendimentos de Geração Distribuída_ is made available under the Open Database License: http://opendatacommons.org/licenses/odbl/1.0/. Any rights in individual contents of the database are licensed under the Database Contents License: http://opendatacommons.org/licenses/dbcl/1.0/

A licença ODbL exige atribuição da fonte e possui cláusula _share-alike_: bases derivadas distribuídas publicamente — incluindo os arquivos das camadas Silver e Gold deste projeto — permanecem sob os mesmos termos.

**IBGE — Censo Demográfico 2022:** dados públicos disponibilizados pelo Instituto Brasileiro de Geografia e Estatística para uso livre, incluindo fins acadêmicos e de pesquisa, mediante citação da fonte.

**Agência Brasil (EBC) — notícias:** conforme os Termos de Uso do portal da EBC, a reprodução é autorizada mediante indicação da fonte, para uso sem finalidade comercial. O projeto é acadêmico e não comercial; cada registro do corpus guarda a URL de origem, e o dashboard exibe a atribuição à Agência Brasil na aba Notícias. A coleta respeita o `robots.txt` do portal.

**Dados a obter via scraping no TP3:** provenientes de páginas públicas de órgãos governamentais, respeitando os termos de uso e o `robots.txt` de cada portal.

## 7. Próximos Passos

- **TP2 (concluído):** camadas Silver e Gold implementadas e validadas; corpus de notícias coletado via BeautifulSoup; dashboard interativo com cache, estado de sessão e upload/download
- **TP3:** coletar a adesão estadual ao Convênio ICMS 16/2015 (CONFAZ) e juntá-la à camada Gold; calcular a taxa de crescimento anual; converter as abas em aplicação multipáginas; expor os dados por meio de API própria (FastAPI); investigar as pendências da seção 3.7
- **TP4:** processar o corpus de notícias com modelo de linguagem local (HuggingFace/Transformers), preenchendo as colunas `resumo` e `sentimento`
- **TP5:** integrar agente inteligente de recomendação ao dashboard final
