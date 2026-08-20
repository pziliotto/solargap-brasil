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
|`DscFonteGeracao`|Filtro da fonte solar|A base inclui também hídrica, eólica, térmica e biogás|
|`CodUFibge`|Chave de junção com o IBGE|Tipo `float64` na origem; requer conversão explícita antes do merge|
|`CodMunicipioIbge`|Chave de junção municipal|Código IBGE de 7 dígitos|
|`DscClasseConsumo`|Segmentação por perfil de consumidor|Análise complementar|
|`DthAtualizaCadastralEmpreend`|Eixo temporal — data de conexão|Validado contra o painel oficial da ANEEL; **ver seção 3.1**|

## 3. Observações sobre Qualidade e Tratamento

- Os dados brutos (ANEEL, IBGE) são armazenados sem alteração em `data/raw/` (camada Bronze) e nunca editados diretamente.
- A limpeza e padronização (nomes de coluna, tipos, remoção de duplicatas) ocorre em `data/interim/` (camada Silver).
- O dado final, já agregado e normalizado por população, fica em `data/processed/` (camada Gold) e alimenta a aplicação.
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

**Tratamento do ano corrente (2026):** os dados cobrem apenas parte do ano (referência 08/2026). Comparações diretas com anos completos são inválidas. Nas visualizações, 2026 é sinalizado como período parcial ou excluído das séries de crescimento anual.

### 3.3 Nota de atualização da fonte

A ANEEL suspendeu temporariamente a atualização dos dados de conexões de MMGD entre 23/09/2025 e 24/10/2025, em razão da migração do sistema SISGD para o novo sistema MMGD. Conexões desse período podem ter sido inseridas retroativamente.

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
|`data/processed/` (Gold)|pequeno|✅ Sim|Alimenta o dashboard; garante reprodutibilidade da aplicação|

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
