# Data Summary Report — SolarGap Brasil

**Projeto:** SolarGap Brasil — Onde está o próximo mercado solar?
**Autora:** Pâmela Lima Ziliotto
**Etapa:** TP3
**Última atualização:** 21/10/2026

---

## 1. Visão Geral

Este relatório documenta as fontes de dados utilizadas no projeto SolarGap Brasil, cujo objetivo é mapear a desigualdade regional na adoção de energia solar distribuída no Brasil, normalizada por população, alinhado aos ODS 7 (Energia Limpa e Acessível) e ODS 10 (Redução das Desigualdades).

**Novidades do TP3:**

- avaliação de novas fontes de notícias, com inclusão da Agência Gov (seção 2.4);
- coleta da adesão estadual ao Convênio ICMS 16/15, do CONFAZ (seção 2.5);
- KPI de taxa de crescimento completo (seção 3.7);
- matriz de oportunidade (seção 3.8);
- camada de serviços compartilhada entre o dashboard multipáginas e a nova API FastAPI (seção 4);
- preparação do corpus para o modelo de linguagem do TP4 (seção 5).

## 2. Fontes de Dados

|Fonte|Conteúdo|Formato|Método de Obtenção|Objetivo de Uso|Estágio|
|---|---|---|---|---|---|
|**ANEEL — Relação de Empreendimentos de Geração Distribuída (MMGD)**|Registro individual de empreendimentos: potência instalada (kW), UF, município, classe de consumo, fonte de geração|ZIP (CSV interno)|Download direto do recurso CKAN|Base principal — potência instalada e empreendimentos por estado|Em uso (TP1–TP3)|
|**ANEEL — Amostra estratificada (derivada)**|Até 40 registros por UF, sem colunas de identificação pessoal|CSV|Derivação local a partir do ZIP (`gerar_amostra.py`)|Referência versionada da estrutura original da base|Em uso (TP1)|
|**IBGE — Censo Demográfico 2022, nível UF**|População residente por Unidade da Federação (27 registros)|JSON|API de Agregados v3 (SIDRA), tabela 9923|Normalização per capita|Em uso (TP1–TP3)|
|**IBGE — Censo Demográfico 2022, nível município**|População residente por município (5.570 registros)|JSON|API de Agregados v3 (SIDRA), tabela 9923|Normalização municipal (análise complementar)|Coletado (TP1)|
|**Agência Brasil (EBC)**|Notícias sobre energia solar e geração distribuída: texto integral, título, linha fina, data e URL (114 notícias, 2014–2026)|HTML → CSV|Web scraping estático (BeautifulSoup)|Nuvem de palavras, estatísticas de texto, contexto por UF; corpus para o LLM|Em uso (TP2–TP3)|
|**Agência Gov (EBC)**|Notícias do governo federal sobre energia, incluindo os boletins mensais da ANEEL sobre MMGD, com dados por estado|HTML → CSV|Web scraping estático (BeautifulSoup): editoria Energia e busca interna|Ampliar o corpus com fonte oficial e de licença aberta|Nova (TP3)|
|**CONFAZ — Convênio ICMS 16/15**|UF, convênio e data de adesão à isenção de ICMS sobre a energia compensada|HTML/texto → CSV|BeautifulSoup + parser do texto legal, com cópia de referência (seção 2.5)|Variável de política pública na análise de disparidade|Nova (TP3)|
|**Notícias enviadas pela API**|Notícias registradas por usuários via `POST /noticias`|JSON → CSV|API própria (FastAPI)|Complementar o corpus com fontes não cobertas pelos scrapers|Nova (TP3)|

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

### 2.3 Corpus de notícias (web scraping multifonte)

**Código:** pacote `src/data_acquisition/noticias/` (substitui o módulo único `noticias.py` do TP2) · **Saída:** `data/processed/corpus_noticias.csv`

**Arquitetura.** As fontes são declaradas em `fontes.py`, cada uma com:

- URL base e licença;
- nível de texto;
- listagens (páginas de tag, editoria ou busca);
- padrão de URL das matérias;
- regras de descarte de parágrafos fixos.

`coletor.py` aplica o mesmo fluxo a todas: listagem → links → matéria (com cache) → extração → filtro de relevância. Incluir uma fonte nova passou a ser uma entrada de configuração, e não um script novo.

**Extração independente do layout.** O pacote não depende de classes CSS, que mudam a cada redesenho do site. A data é procurada nesta ordem, até ser encontrada:

1. o padrão de texto da própria fonte (ex.: "Publicado em DD/MM/AAAA - HH:MM", na Agência Brasil);
2. a meta tag `article:published_time`;
3. as meta tags Dublin Core (`DC.date.created`, usadas pela Agência Gov);
4. o `datePublished` do JSON-LD.

Título e linha fina vêm das meta tags Open Graph. O corpo é o elemento cujos parágrafos `<p>` somam mais texto. Parágrafos fixos da fonte (aviso de reprodução, link de origem) são descartados para não poluir o corpus nem a entrada do modelo de linguagem.

**Navegação educada.**

- O `robots.txt` é lido uma vez por domínio, com o próprio User-Agent do projeto, e consultado antes de cada URL. O leitor padrão do Python se identifica como "Python-urllib", nome que alguns sites bloqueiam, o que produziria um falso "proibido".
- Um `robots.txt` ilegível significa não coletar o domínio.
- O `Crawl-delay` é respeitado quando maior que a pausa padrão de 1,5 segundo.
- Há retry com espera exponencial, reaproveitando `calcular_espera_backoff` do `coletor_base.py`.
- O HTML de cada matéria fica em `data/raw/html/<fonte>/` (Bronze, não versionado).

**Mescla incremental.** O corpus versionado é o ponto de partida de cada execução:

- Notícias já presentes são preservadas como estão, inclusive `resumo` e `sentimento`, que o LLM preencherá no TP4. Uma nova coleta nunca apaga o trabalho do modelo.
- Só ids novos são baixados.
- A opção `--reprocessar` reextrai a partir do cache, ainda preservando as colunas do modelo.
- A mesma notícia publicada por duas fontes (mesmo título normalizado) é mantida uma única vez, com preferência pelo registro de texto integral.

Um teste automatizado garante que reexecutar a mescla sem notícias novas reproduz o arquivo versionado byte a byte.

**Agência Gov — método.** O portal usa o CMS Plone, com HTML estático. O coletor percorre duas origens:

- **Editoria Energia** (`/noticias/energia`): é ampla (petróleo, mineração), por isso só segue os links cujo título menciona solar ou geração distribuída;
- **Busca interna** (`/@@search`) pelos termos "energia solar", "geração distribuída", "micro e minigeração" e "fotovoltaica", com paginação `b_start`.

Os links válidos seguem o padrão `/noticias/AAAAMM/<slug>`.

**Situação da coleta.** A Agência Brasil mantém as 114 notícias coletadas em 21/09/2026: período de 27/06/2014 a 08/07/2026, tamanho médio de 3.019 caracteres e UFs mais mencionadas SP (20), RJ (16), MG (12), BA (11) e PR (10). O coletor da Agência Gov foi implementado e testado com páginas de exemplo que reproduzem a estrutura do portal; a primeira coleta real ocorre ao executar `python -m src.data_acquisition.noticias`, e o resumo por fonte fica registrado no log da execução.

**Esquema do corpus** (contrato único em `esquema.COLUNAS_CORPUS`, compartilhado por scrapers, API, dashboard e, no TP4, o modelo de linguagem):

|Coluna|Conteúdo|
|---|---|
|`id`|Hash MD5 da URL (12 caracteres), gerado por `esquema.id_noticia()` — a mesma regra no scraper e na API|
|`fonte`, `url`, `tag_origem`|Origem e rastreabilidade (`tag_origem = envio_api` para notícias enviadas pela API)|
|`data_publicacao`, `coletado_em`|Data da notícia e data da coleta|
|`titulo`, `linha_fina`, `texto`|Conteúdo textual; `texto` vazio no nível "metadados"|
|`ufs_mencionadas`|Siglas das UFs citadas, por expressão regular com fronteira de palavra ("Mato Grosso" não casa com "Mato Grosso do Sul")|
|`nivel_texto`|`integral` ou `metadados` — o que a licença da fonte permite guardar (seção 2.4)|
|`resumo`, `sentimento`|Vazias até o TP4; preenchidas pelo modelo de linguagem sem alteração de esquema|

### 2.4 Avaliação de novas fontes de notícias

Fontes avaliadas para ampliar o corpus, com foco em energia solar. Os critérios, aplicados nesta ordem, foram:

1. **Acesso liberado:** conteúdo sem paywall.
2. **Termos de uso:** a reprodução é autorizada? A coleta automatizada é proibida? O repositório é público, e copiar texto sem autorização seria redistribuir conteúdo protegido.
3. **robots.txt:** verificado em toda execução.
4. **Estrutura:** HTML estático (BeautifulSoup) ou dinâmico (Selenium).

|Fonte|Acesso|Termos / licença|Decisão|
|---|---|---|---|
|Agência Brasil (EBC)|Livre|Reprodução autorizada mediante indicação da fonte|Mantida — texto integral|
|**Agência Gov (EBC)**|Livre|Cada matéria informa: "A reprodução é gratuita desde que citada a fonte"|**Incluída — texto integral**|
|eixos (antiga epbr)|Livre (o produto "eixos PRO" é pago)|Uso pessoal e não comercial; proíbe copiar, baixar ou manter cache sem autorização por escrito|Configurada só com metadados (feed RSS) e **desabilitada** até autorização da agência|
|g1 / Globo|Livre|Os termos gerais da Globo autorizam indexação automatizada apenas por buscadores públicos, para exibir links|Excluída|
|CNN Brasil|Livre|Termos de uso não localizados na avaliação; todos os direitos reservados|Não incluída até verificação|
|Portal R7|Livre|Termos de uso não localizados na avaliação; todos os direitos reservados|Não incluída até verificação|
|CanalEnergia|Assinatura|—|Excluída: conteúdo sem acesso liberado|
|MegaWhat|Assinatura|—|Excluída: conteúdo sem acesso liberado|
|Canal Solar|Livre|Pede contato prévio para reutilizar o material|Excluída|

**Nível de texto proporcional à licença.** Fontes com autorização de reprodução entram no nível `integral`, com o texto completo. Para fontes sem essa autorização, o projeto prevê o nível `metadados`: só título, linha fina, data e link, lidos do feed RSS que o próprio veículo publica para leitores automáticos. Nesse nível nenhuma matéria é baixada nem guardada. O mecanismo está implementado e testado (fonte eixos), mas desabilitado: habilitá-lo depende de autorização, que pode ser solicitada pelo contato informado no site do veículo.

**Selenium.** Nenhuma fonte viável exige renderização por JavaScript: listagens, matérias e feeds chegam completos no HTML/XML. Seguindo a orientação do enunciado de manter a simplicidade, o projeto não usa Selenium.

### 2.5 Adesão ao Convênio ICMS 16/15 (CONFAZ)

**Código:** `src/data_acquisition/icms_confaz.py` · **Saída:** `data/processed/gold_icms_uf.csv` (27 linhas)

**O que é.** O Convênio ICMS 16/15 autoriza os estados a isentar de ICMS a energia compensada na micro e minigeração distribuída. As adesões ocorreram entre 2015 e 2018, o que dá ao projeto uma variável de política pública com variação entre UFs.

**Fonte e restrição de acesso.** A fonte primária é a página oficial do convênio no CONFAZ. Na avaliação do TP3, o `robots.txt` do CONFAZ bloqueou o acesso automatizado. O coletor respeita essa regra:

- consulta o `robots.txt` com o User-Agent do projeto a cada execução e só baixa a página oficial se o acesso for permitido;
- caso contrário, usa a cópia de referência do texto oficial em `data/external/confaz/convenio_icms_16_15.txt`, com as notas de adesão e as redações da cláusula primeira, conforme reproduzidas pela Sefaz-MT em 25/06/2021, mais a alteração posterior do Convênio ICMS 114/23.

Convênios são atos oficiais e não têm proteção autoral (Lei 9.610/98, art. 8º, IV). A origem efetiva fica registrada em cada linha (coluna `origem_texto`).

**Interpretação do texto legal.** O parser lê quatro elementos:

- **Redação original da cláusula primeira** (GO, PE e SP): a data de adesão é a da ratificação nacional, 14/05/2015.
- **Notas de adesão**, no formato "Adesão de XX e YY, a partir de DD.MM.AA, pelo Conv. ICMS NN/AA".
- **UFs presentes só numa nova redação da cláusula, sem nota de adesão própria:** PB, PI, RO e SE, pelo Conv. ICMS 75/16, com efeitos a partir de 01/09/2016. Essa inclusão é **inferida da redação** e vem sinalizada na coluna `observacao`.
- **Limite de prazo do § 3º:** o Conv. ICMS 42/18 limitou o benefício de PR e SC a 48 meses; o Conv. ICMS 114/23 manteve o limite apenas para o PR.

Como a cláusula terceira fixa efeitos a partir de 01/09/2015, adesões anteriores a essa data têm `inicio_efeitos` igual a 01/09/2015.

**Resultado.**

|Início da isenção|UFs|
|---|---|
|2015|AC, AL, BA, CE, DF, GO, MA, MG, MT, PE, RJ, RN, RS, SP, TO|
|2016|MS, PA, PB, PI, RO, RR, SE|
|2017|AP|
|2018|AM, ES, PR, SC|

**Validações automáticas:** 27 UFs, cada uma uma única vez; a redação vigente da cláusula primeira lista as 27.

**Achado analítico.** A correlação de Spearman entre o tempo de isenção e a adoção per capita é de **−0,06**, ou seja, nenhuma relação. Entre as 15 UFs com isenção desde 2015, oito estão abaixo da média nacional de adoção (AL, AC, BA, CE, PE, SP, RJ e DF). Entre as que aderiram a partir de 2017, quatro estão acima (AP, ES, PR e SC). A isenção de ICMS é condição favorável, mas não explica sozinha a disparidade. Correlação não é causalidade, e a amostra tem 27 UFs.

**Modelagem.** A tabela é uma dimensão própria da Gold, unida por `sigla_uf` sob demanda no dashboard e na API. No TP2 o plano era juntá-la ao `gold_uf.csv` dentro do `construir_gold.py`; essa junção foi removida para que atualizar a política não exija reprocessar 4,6 milhões de registros, nem ter a base da ANEEL.

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

### 3.7 Taxa de crescimento (KPI concluído no TP3)

**Definição.** O indicador mede o crescimento do **parque instalado** (potência acumulada), e não da potência conectada em cada ano. A base da ANEEL é um retrato dos empreendimentos ativos. O parque ao fim de cada ano é reconstruído somando as conexões desde 2012, com grade completa de UF × ano: anos sem conexões entram com zero, para que o acumulado seja carregado adiante.

- **Crescimento anual:** parque no fim do ano ÷ parque no fim do ano anterior − 1.
- **CAGR da janela:** (parque final ÷ parque inicial)^(1/anos) − 1.

**Por que o estoque, e não o fluxo.** Em 2023 entraram menos sistemas que em 2022, por causa da corrida para conectar antes do fim da isenção do Fio B. O parque, porém, continuou crescendo. Medir o fluxo confundiria desaceleração das novas conexões com retração do mercado.

**Janela padrão: 2022–2025.** 2022 é o ano da Lei 14.300, recorte central do projeto, e 2025 é o último ano completo. Janelas que começam perto de 2012 produzem taxas sem significado, porque estados com parque quase nulo exibem crescimentos de milhares de por cento. O usuário pode escolher outra janela no dashboard e na API, sempre com anos completos.

**Resultado.** O parque solar distribuído passou de 9,9 GW (2021) para 18,3 GW (2022), 27,1 GW (2023), 37,8 GW (2024) e 47,5 GW (2025), chegando a 51,3 GW até agosto de 2026. O crescimento anual desacelera: 84,0%, 48,0%, 39,9% e 25,7%. O CAGR de 2022 a 2025 é de **37,5% ao ano**.

### 3.8 Matriz de oportunidade

Cruza a adoção per capita (W/hab acumulado até agosto de 2026) com o crescimento do parque (CAGR 2022–2025). As referências são nacionais: 252,7 W/hab (total do país ÷ população, e não média simples das UFs) e 37,5% ao ano.

|Quadrante|Leitura|UFs (visão corrigida)|
|---|---|---|
|Líder em expansão|Adoção e crescimento acima da referência|AP, RO, ES, TO, MT, GO, RN, MS, PI, MA|
|Mercado maduro|Adoção acima, crescimento abaixo|PR, SC, MG, RS|
|**Mercado emergente**|Adoção abaixo, crescimento acima — **o próximo mercado solar**|RR, AL, AC, BA, PA, AM, CE, PE, SP, SE|
|**Lacuna persistente**|Adoção e crescimento abaixo — **foco de política pública (ODS 10)**|RJ, DF, PB|

**Sensibilidade à correção do Maranhão.** No critério do painel oficial da ANEEL, sem os registros imputados, o Maranhão cai de 279 para 155 W/hab e passa de "líder em expansão" para "lacuna persistente". A decisão de qualidade de dados documentada na seção 3.4 muda, portanto, a recomendação de política pública para o estado. O dashboard e a API permitem alternar entre as duas visões.

**Ressalva.** UFs com parque pequeno em 2022 tendem a exibir taxas altas; o caso extremo é o AP, com 105,8% ao ano. O tamanho do círculo no gráfico (potência absoluta) e a ficha da UF na API (`/ufs/{sigla}`, com os parques inicial e final) tornam isso visível.

### 3.9 Pendências

|Item|Situação|
|---|---|
|Classe de consumo `REBR`|39.946 registros em 14 UFs, sem significado documentado. Mantida sem alteração até consulta ao dicionário de dados da ANEEL|
|Divergência de potência com o painel oficial|Ver seção 3.6|
|Primeira coleta real da Agência Gov|Coletor testado com páginas de exemplo; números a registrar após a execução local|
|Inclusão de PB, PI, RO e SE no Convênio 16/15|Inferida da redação dada pelo Conv. ICMS 75/16. Confirmar no texto consolidado atual do CONFAZ, por consulta manual|
|Termos de uso de CNN Brasil e R7|Não localizados; as fontes permanecem fora do corpus até verificação|

## 4. Integração e Uso dos Dados

### 4.1 Camada de serviços

O dashboard e a API calculam os mesmos indicadores. Para que os números nunca divirjam, a regra de negócio saiu de `src/app/carregamento.py` (TP2) e passou para `src/servicos/`, em pandas puro, sem dependência de Streamlit ou FastAPI:

|Módulo|Responsabilidade|
|---|---|
|`dados.py`|Leitura da Gold e das contribuições externas; arquivo obrigatório ausente vira a exceção `DadosIndisponiveis`|
|`indicadores.py`|Indicadores per capita, ranking, séries, crescimento, matriz de oportunidade e correlação de Spearman|
|`noticias.py`|Filtros do corpus e registro de notícias enviadas pela API|
|`texto.py`|Frequência de termos, detecção de UFs e montagem da entrada do LLM|

O dashboard envolve essas funções com `st.cache_data`; a API as chama a partir de um repositório carregado uma única vez no startup.

### 4.2 Dashboard multipáginas

Arquivo de entrada: `src/app/app.py`, com `st.navigation`, menu agrupado em seções e filtros globais desenhados uma única vez.

|Seção|Página|Dados|O que o usuário faz|
|---|---|---|---|
|Visão geral|Início|Gold|Problema, objetivo, números do Brasil e guia de navegação|
|Análises|Panorama|`gold_mmgd_agregado`, `gold_uf`|Ranking das 27 UFs na métrica escolhida, com média nacional e destaque de uma UF|
|Análises|Evolução e crescimento|`gold_mmgd_agregado`|Conexões por ano; crescimento anual do parque; CAGR por UF em janela escolhida|
|Análises|Oportunidades|Gold + `gold_icms_uf`|Matriz de oportunidade; isenção de ICMS × adoção|
|Contexto|Notícias|corpus + enviadas|Filtros por fonte e UF, nuvem de palavras, termos, volume por ano e fonte, tabela com links|
|Ferramentas|Dados|todas|Download dos recortes; upload de indicador próprio para comparação|
|Ferramentas|API|API|Status, explorador de rotas GET e envio de notícia (POST)|

**Estado de sessão entre páginas.** O Streamlit apaga o valor de um widget que deixa de ser desenhado. Como os filtros só aparecem nas páginas de análise, cada valor é copiado para uma chave auxiliar no `on_change` e restaurado antes de o widget ser desenhado (`componentes.widget_persistente`). Assim, os filtros sobrevivem à passagem por páginas sem filtros.

**Resiliência.** As páginas de análise leem a Gold diretamente, pela camada de serviços, e funcionam sem a API no ar. A API é a porta de escrita (POST) e de consumo externo.

### 4.3 API (FastAPI)

São 13 rotas em `src/api/`, documentadas em `docs/api.md` e em `/docs` (Swagger). Todas as respostas usam modelos Pydantic (`response_model`). Os erros seguem um formato único (`{"detail": ...}`):

- **400** filtros incoerentes;
- **404** recurso inexistente;
- **409** notícia duplicada;
- **422** validação dos dados enviados;
- **503** dados indisponíveis;
- **500** erro inesperado, registrado no log, sem rastro de pilha para o cliente.

As duas rotas de envio são:

- `POST /noticias`: valida URL, tamanhos e data (entre 2012 e hoje), recusa URLs repetidas e detecta as UFs. Grava em `data/external/noticias_enviadas.csv`, arquivo separado do corpus coletado para que uma nova raspagem não sobrescreva as contribuições.
- `POST /comparacoes`: recebe um indicador por UF e devolve posições, diferença de posições e correlação de Spearman com a adoção. É a versão em API do upload da página Dados.

### 4.4 Testes

São 67 testes automatizados (`python -m pytest`):

- **Serviços:** reprodução exata do `gold_uf.csv`, filtros, monotonia do parque, CAGR e quadrantes.
- **API:** todas as rotas e todos os códigos de erro.
- **Scrapers:** extração das duas fontes, `robots.txt` bloqueando, cache, RSS sem texto integral e preservação de `resumo`/`sentimento` na mescla.
- **ICMS:** datas por UF, inferências e § 3º.
- **Gold:** execução com Silver sintética.
- **Upload.**
- **Dashboard:** todas as páginas via `AppTest` e persistência dos filtros.

Também foi executado um teste de integração real, com a API no uvicorn e a página API do dashboard enviando uma notícia por HTTP: a resposta foi 201 e o reenvio, 409.

## 5. Preparação para o Modelo de Linguagem (TP4)

|Tarefa de LLM (enunciado)|Dados disponíveis|Aplicação no SolarGap|
|---|---|---|
|Classificação de sentimentos|Corpus multifonte; títulos e linhas finas também no nível "metadados"|Tom das notícias sobre GD por UF (positivo, neutro, negativo), comparado à adoção: a imprensa acompanha o mercado?|
|Análise de texto (resumo)|Textos integrais (média de ~3 mil caracteres)|Resumo de cada notícia na página Notícias|
|Perguntas e respostas|Gold + corpus + ICMS, expostos pela API|Base do agente do TP5: perguntas como "por que o RJ é lacuna persistente?" respondidas com as rotas da API|
|Geração de texto|Ficha da UF (`/ufs/{sigla}`)|Relatório descritivo automático por estado|

**O que já está pronto.**

1. As colunas `resumo` e `sentimento` existem no esquema (nulas).
2. A mescla do coletor nunca apaga o que o modelo preencher.
3. `texto_para_modelo` (em `servicos/texto.py`) monta a entrada do modelo respeitando a licença: uma notícia de nível "metadados" nunca envia texto integral. O limite de 4.000 caracteres (~1.000 tokens) cabe em modelos locais pequenos.
4. A API já devolve `texto_para_modelo` em `GET /noticias/{id}`.
5. A rota `POST /processar_texto` do TP4 seguirá o padrão já implementado: modelo Pydantic de entrada e de resposta, e erro 503 se o modelo não carregar.

**Ponto de atenção de licença para o TP4.** Resumos gerados por LLM são obras derivadas. Agência Brasil e Agência Gov autorizam reprodução com citação. Cada resumo manterá a URL de origem.

## 6. Governança e Privacidade

A base original da ANEEL contém duas colunas com dado pessoal identificável: `NumCPFCNPJ` e `NomTitularEmpreendimento`.

Como o repositório é público e nenhum indicador depende da identificação do titular, essas colunas são **excluídas na leitura** (parâmetro `usecols` do pandas), e não removidas após o carregamento. O dado sensível nunca é carregado em memória nem gravado em disco pelos artefatos do projeto, em conformidade com o princípio de minimização de dados. O mesmo filtro vale para a amostra versionada e para as camadas Silver e Gold.

**Arquivos enviados pelo usuário (dashboard).** O conteúdo do upload permanece apenas na sessão do navegador (`st.session_state`) e não é gravado nem versionado.

**Notícias enviadas pela API.** São gravadas em `data/external/noticias_enviadas.csv`, fora do versionamento. Contêm apenas dados da notícia (fonte, URL, título, data, textos), nenhum dado de quem enviou.

**Conteúdo de terceiros.** O nível de texto de cada fonte segue a licença (seção 2.4). Nenhum texto de fonte sem autorização de reprodução é armazenado.

## 7. Versionamento e Reprodutibilidade

|Artefato|Tamanho|Versionado no Git|Justificativa|
|---|---|---|---|
|ANEEL — ZIP completo|~105 MiB (CSV interno ~1,4 GB)|❌ Não|Excede o limite de 100 MB por arquivo do GitHub|
|ANEEL — amostra estratificada|< 1 MB|✅ Sim|Referência da estrutura original da base, sem dados pessoais|
|IBGE — UF e municípios|~0,01 MB e ~1,9 MB|✅ Sim|Volume aceitável|
|`data/interim/` (Silver)|—|❌ Não|Sempre reproduzível a partir da Bronze|
|`gold_mmgd_agregado.csv`, `gold_uf.csv`|81 KB, 2 KB|✅ Sim|Alimentam o dashboard e a API sem a base completa|
|`gold_icms_uf.csv`|~3,5 KB|✅ Sim|Dimensão de política pública (TP3)|
|`corpus_noticias.csv`|< 1 MB|✅ Sim|Corpus para o dashboard, a API e o LLM do TP4|
|`data/external/confaz/`|~8 KB|✅ Sim|Cópia de referência do texto oficial do Convênio ICMS 16/15|
|`data/external/noticias_enviadas.csv`|—|❌ Não|Estado de execução da API, não dado do projeto|
|`data/raw/html/` (cache dos scrapers)|—|❌ Não|Reproduzível executando os coletores|

**Regeneração:** `python -m src.data_acquisition.aneel`, `...noticias` e `...icms_confaz`, seguidos de `python -m src.preparacao.construir_silver` e `...construir_gold`, sempre a partir da raiz.

⚠️ **Restrições de acesso:** o portal da ANEEL filtra por IP (fora do Brasil, é preciso VPN com saída no Brasil); o `robots.txt` do CONFAZ bloqueou o acesso automatizado (seção 2.5). Nenhuma das duas afeta a avaliação: a Gold e as referências estão versionadas.

## 8. Licenciamento e Uso

**ANEEL — Relação de Empreendimentos de Geração Distribuída (MMGD):**

> This _Relação de Empreendimentos de Geração Distribuída_ is made available under the Open Database License: http://opendatacommons.org/licenses/odbl/1.0/. Any rights in individual contents of the database are licensed under the Database Contents License: http://opendatacommons.org/licenses/dbcl/1.0/

A ODbL exige atribuição e tem cláusula _share-alike_: bases derivadas distribuídas publicamente, incluindo as camadas Silver e Gold, permanecem sob os mesmos termos. A API repete a licença em seus metadados (`/docs`).

**IBGE — Censo Demográfico 2022:** uso livre, inclusive acadêmico, mediante citação da fonte.

**Agência Brasil e Agência Gov (EBC):** reprodução autorizada mediante indicação da fonte, sem finalidade comercial (termos da EBC; aviso explícito em cada matéria da Agência Gov). Cada registro guarda a URL de origem, e o dashboard exibe a atribuição na página Notícias.

**CONFAZ — Convênio ICMS 16/15:** ato oficial, sem proteção autoral (Lei 9.610/98, art. 8º, IV). A coleta automatizada respeita o `robots.txt`.

**Veículos privados avaliados:** ver seção 2.4. Nenhum conteúdo é armazenado sem autorização compatível.

## 9. Próximos Passos

- **TP3 (concluído):**
  - dashboard multipáginas;
  - API FastAPI com 13 rotas;
  - camada de serviços compartilhada;
  - Agência Gov e CONFAZ como novas fontes;
  - KPI de crescimento e matriz de oportunidade;
  - 67 testes automatizados.
- **TP4:**
  - escolher e documentar um modelo local da HuggingFace (ex.: BERTimbau para sentimento; PTT5 ou mT5 para resumo), avaliando desempenho, custo computacional local e acessibilidade;
  - implementar `POST /processar_texto` com modelos de resposta e erro 503 se o modelo não carregar;
  - preencher `resumo` e `sentimento` no corpus.
- **TP5:**
  - agente inteligente de recomendação que use as rotas da API como ferramentas;
  - dashboard final consolidado.
