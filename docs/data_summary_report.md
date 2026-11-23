# Data Summary Report — SolarGap Brasil

**Projeto:** SolarGap Brasil — Onde está o próximo mercado solar?
**Autora:** Pâmela Lima Ziliotto
**Etapa:** TP5 — entrega final (base ANEEL de referência 10/2026)
**Última atualização:** 23/11/2026

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
|`DscFonteGeracao`|Filtro da fonte solar|A base inclui também hídrica, eólica, térmica e biogás. Vazio em 156 registros na base 10/2026 (73.501 na base 08/2026, 99,8% no MA); **ver seção 3.4**|
|`CodUFibge`|Chave de junção com o IBGE|Tipo `float64` na origem; requer conversão explícita antes do merge|
|`CodMunicipioIbge`|Chave de junção municipal|Código IBGE de 7 dígitos|
|`DscClasseConsumo`|Segmentação por perfil de consumidor|Análise complementar|
|`DthAtualizaCadastralEmpreend`|Eixo temporal — data de conexão|Validado contra o painel oficial da ANEEL; **ver seção 3.1**|
|`SigTipoGeracao`|Verificação da fonte de geração|Sigla do tipo de usina (UFV, UTE, EOL, CGH). Correspondência de 100% entre `UFV` e "Radiação solar"; vazio nos mesmos registros em que `DscFonteGeracao` é vazio|
|`SigAgente`|Distribuidora (`distribuidora` na Silver)|Diagnóstico da potência suspeita por distribuidora; **ver seção 3.4.3** (TP4.5)|
|`DscModalidadeHabilitado`|Modalidade (`modalidade` na Silver)|Geração na própria UC, autoconsumo remoto, compartilhada, condomínio; usada no potencial municipal (TP4.5)|

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
- A interpretação usa a biblioteca `protego`, que segue a RFC 9309, inclusive os curingas `*` e `$` (ver "Correção de conformidade com o robots.txt", abaixo).
- Um `robots.txt` ilegível significa não coletar o domínio.
- O `Crawl-delay` é respeitado quando maior que a pausa padrão de 1,5 segundo.
- Há retry com espera exponencial, reaproveitando `calcular_espera_backoff` do `coletor_base.py`.
- Respostas que não são texto (vídeo, imagem) são descartadas sem ir para o cache, e uma página que quebra a extração é registrada no log sem derrubar a fonte.
- O HTML de cada matéria fica em `data/raw/html/<fonte>/` (Bronze, não versionado).

**Mescla incremental.** O corpus versionado é o ponto de partida de cada execução:

- Notícias já presentes são preservadas como estão, inclusive `resumo` e `sentimento`, que o LLM preencherá no TP4. Uma nova coleta nunca apaga o trabalho do modelo.
- Só ids novos são baixados.
- A opção `--reprocessar` reextrai a partir do cache, ainda preservando as colunas do modelo.
- A mesma notícia publicada por duas fontes (mesmo título normalizado) é mantida uma única vez, com preferência pelo registro de texto integral.

Um teste automatizado garante que reexecutar a mescla sem notícias novas reproduz o arquivo versionado byte a byte.

**Agência Gov — método.** O portal usa o CMS Plone, com HTML estático. O coletor percorre duas origens:

- **Editoria Energia** (`/noticias/energia`): é ampla (petróleo, mineração), por isso só segue os links cujo título menciona solar ou geração distribuída;
- **Sitemap** (`/sitemap.xml.gz`), indicado no próprio `robots.txt` do portal: todas as matérias listadas são baixadas e passam pelo filtro de relevância.

Os links válidos seguem o padrão `/noticias/AAAAMM/<slug>`. O sitemap também lista imagens nesse caminho (`.jpg`, `.png`), que o padrão descarta; em 20/11/2026 ele tinha 799 matérias, de 08/2023 a 10/2026, concentradas nos meses recentes.

**Agência Brasil — tags.** Além das cinco tags originais (`energia-solar-1`, `energia-solar`, `geracao-distribuida`, `energia-renovavel`, `energias-renovaveis`), a coleta de 20/11/2026 incluiu as tags que existem no portal para as palavras-chave do benchmark v2: `micro-geracao`, `minigeracao`, `fotovoltaica`, `energia-fotovoltaica`, `paineis-solares`, `placas-solares`, `net-metering`, `geracao-de-energia-solar`, `usina-solar` e `usinas-solares`. Não existem tags para Lei 14.300, fio B, compensação de energia ou de créditos, nem `microgeracao` e `micro-e-minigeracao` (todas responderam 404). A busca do portal (`/search/`) é proibida pelo `robots.txt` e não é usada.

**Filtro de relevância da coleta** (`base.PADRAO_RELEVANCIA`, distinto da relevância do modelo de IA): basta a notícia mencionar o tema. Desde 20/11/2026 inclui também "Lei 14.300" (com e sem ponto, com "nº" opcional), "fio B", "compensação de créditos" (exceto "de carbono"), "net metering", geração distribuída, microgeração e minigeração, todos com limite de palavra, para que "fio B" não case em "fio branco" nem "GD" em "GDF". Exemplos positivos e negativos estão nos testes.

**Correção de conformidade com o robots.txt (20/11/2026).** O `robots.txt` da Agência Gov contém `Disallow: /*?`, que pela RFC 9309 proíbe toda URL com parâmetros, inclusive a busca interna (`/@@search?SearchableText=...`) que o coletor usava como listagem. O leitor padrão do Python (`urllib.robotparser`) não entende curingas: tratava `/*?` como caminho literal e respondia "permitido". Com isso, a coleta de 21/10/2026 descobriu as matérias da Agência Gov por um caminho que o site proíbe. As páginas das matérias em si eram permitidas.

Providências:

1. O `Navegador` passou a usar a biblioteca `protego` (RFC 9309). Os testes usam os `robots.txt` reais das duas agências, salvos em `tests/fixtures/`. Eles cobrem a busca da Agência Gov bloqueada, as matérias, a editoria e o sitemap permitidos, o `/search/` da Agência Brasil bloqueado, as tags paginadas (`?page=N`) permitidas e o `Crawl-delay` de 10 s. Também verificam que nenhuma listagem configurada é proibida.
2. A busca interna foi retirada da configuração da Agência Gov, que passou a ser descoberta pelo sitemap.
3. As **6 notícias** da Agência Gov descobertas pela busca, que eram todas as dessa fonte no corpus, foram removidas do `corpus_noticias.csv` e do `corpus_ia.csv`. Removê-las não muda nenhuma outra linha.
4. O sitemap redescobriu **4** delas, que voltaram com `tag_origem = sitemap`: datacenter, hidrogênio, Reduc e a multa à Coelba. As outras **2** não estão no sitemap e ficaram fora do corpus: chuva de meteoros Orionídeas e os 199 anos do Observatório Nacional, que citam "Sistema Solar" de passagem.
5. As 6 continuam no gabarito `docs/benchmark/rotulos_benchmark.csv`, que não foi alterado. As 4 que voltaram têm o mesmo `id` (hash da URL), e o benchmark as encontra no corpus. As 2 que não voltaram ficam sem texto numa nova execução do benchmark: são duas das 7 notícias "fora do tema" (seção 5.2). Os resultados publicados em `docs/escolha_modelo.md` foram medidos antes da correção, com as 30 notícias.

**Situação da coleta.** Em 20/11/2026, a coleta ampliada trouxe **24 notícias novas**: 21 da Agência Brasil, de 2015 a 2026, pelas tags novas e por páginas antigas das tags originais, e 3 da Agência Gov, pelo sitemap. Somadas às 4 redescobertas, o corpus chegou a 141 notícias: 134 da Agência Brasil e 7 da Agência Gov. Essas 28 (24 novas e 4 redescobertas) foram processadas pelos modelos de IA (`corpus_ia.csv`) com a configuração atual; as 113 linhas já processadas não mudaram.

Na mesma data entraram as duas fontes do gov.br (seção 2.4):

| Fonte | Descoberta | Examinadas | No corpus | GD sem "solar" |
|---|---|---|---|---|
| ANEEL | sitemap | 2.355 matérias (2.054 descartadas pelo filtro de relevância) | 298 (301 relevantes; 3 já estavam no corpus por outra fonte) | 70 |
| MME | listagem paginada, com pré-filtro pelo título | 5.839 links (5.723 descartados pelo título; 2 com erro 500 no servidor) | 114 | 8 |

"GD sem solar" conta as notícias que mencionam um termo de geração distribuída (Lei 14.300, fio B, compensação de créditos, micro ou minigeração, MMGD) e não citam "solar" nem "fotovoltaica". Nas agências da EBC esse caso quase não aparece: são 2 notícias em 141. O corpus passou a ter **553 notícias**: ANEEL 298, Agência Brasil 134, MME 114 e Agência Gov 7. As 412 da ANEEL e do MME ainda não passaram pelo processamento de IA e aparecem como "não avaliadas".

Limitação do MME: o pré-filtro pelo título deixa de fora as notícias que só tratam de GD no corpo do texto.

Três ajustes de coleta surgiram com essas fontes, todos com testes:

- **Paginação com pré-filtro:** uma página de listagem sem nenhum título relevante encerrava a paginação. Agora ela só termina quando a página não traz nenhum link de matéria.
- **Nomes de cache:** slugs da ANEEL com mais de 200 caracteres estouravam o limite de 260 caracteres de caminho do Windows, e a falha derrubava a fonte. Nomes longos agora são encurtados com um hash do caminho, e uma falha ao gravar o cache não interrompe mais a coleta.
- **Rodapé do MME:** o contato da assessoria e os links de redes sociais, que fecham as matérias do MME, passaram a ser descartados como parágrafos fixos.

Situação anterior: a Agência Brasil mantinha as 114 notícias coletadas em 21/09/2026: período de 27/06/2014 a 08/07/2026, tamanho médio de 3.019 caracteres e UFs mais mencionadas SP (20), RJ (16), MG (12), BA (11) e PR (10).

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
|**ANEEL (gov.br)**|Livre|Rodapé de todo o gov.br: "Todo o conteúdo deste site está publicado sob a licença Creative Commons Atribuição-SemDerivações 3.0 Não Adaptada"|**Incluída em 20/11/2026 — texto integral**|
|**MME (gov.br)**|Livre|Mesma licença do gov.br (CC BY-ND 3.0)|**Incluída em 20/11/2026 — texto integral**|
|eixos (antiga epbr)|Livre (o produto "eixos PRO" é pago)|Uso pessoal e não comercial; proíbe copiar, baixar ou manter cache sem autorização por escrito|Configurada só com metadados (feed RSS) e **desabilitada** até autorização da agência|
|g1 / Globo|Livre|Os termos gerais da Globo autorizam indexação automatizada apenas por buscadores públicos, para exibir links|Excluída|
|CNN Brasil|Livre|Termos de uso não localizados na avaliação; todos os direitos reservados|Não incluída até verificação|
|Portal R7|Livre|Termos de uso não localizados na avaliação; todos os direitos reservados|Não incluída até verificação|
|CanalEnergia|Assinatura|—|Excluída: conteúdo sem acesso liberado|
|MegaWhat|Assinatura|—|Excluída: conteúdo sem acesso liberado|
|Canal Solar|Livre|Pede contato prévio para reutilizar o material|Excluída|

**ANEEL e MME (avaliação de 20/11/2026).** As duas fontes foram avaliadas para trazer notícias de geração distribuída que não citam "solar" (Lei 14.300, MMGD, compensação de energia), caso pouco presente nas agências da EBC. Pelos quatro critérios:

1. **Acesso:** livre, sem cadastro.
2. **Termos e licença:** todo o gov.br está sob CC BY-ND 3.0, que autoriza copiar e redistribuir o conteúdo literalmente, inclusive em repositório público, desde que citada a fonte. Os Termos de Uso do gov.br (`/pt-br/termos-de-uso`) tratam de cookies e do uso dos serviços e não proíbem coleta automatizada. **Ressalva:** a cláusula "SemDerivações" proíbe distribuir obra adaptada. O texto do corpus é literal e cumpre a licença. Já o resumo gerado pelo modelo (`corpus_ia.csv`) é curto e não reproduz a obra, mas a fronteira entre resumo e adaptação não é nítida: se o projeto quiser eliminar esse risco, basta não publicar o resumo dessas duas fontes e manter só a relevância.

**Decisão sobre a cláusula SemDerivações (22/11/2026).** O projeto não gera, não guarda e não exibe resumo automático das fontes do gov.br. Elas são ANEEL, MME e **Agência Gov**, incluída pela autora na mesma regra por ser o portal de notícias do governo federal. Para essas fontes, o painel e a API mostram título, link para a matéria original, fonte e a classificação de relevância. O resumo continua para as fontes cuja licença permite derivações (Agência Brasil). Implementação:

- **Regra única:** `esquema.FONTES_SEM_DERIVACAO`, conferida por teste contra `permite_derivacao=False` no cadastro de fontes (`fontes.py`).
- **Painel e API:** `servicos/dados.anexar_ia` apaga o resumo dessas fontes, e as duas camadas leem por ele. Na tabela da página Notícias, a coluna de resumo mostra "licença CC BY-ND: abra a original".
- **Processamento de uma notícia:** em `POST /noticias/{id}/processar`, o padrão passa a ser só a relevância, e pedir o resumo explicitamente devolve 403.
- **Lote:** `processar_corpus` não gera resumo para essas fontes. Os 7 resumos da Agência Gov que já estavam em `corpus_ia.csv` foram removidos do arquivo atual, sem alterar nenhuma outra linha. Eles **continuam no histórico do Git**, nos commits até 4d1b386. O histórico não foi reescrito: reescrever commits já publicados quebraria os clones existentes, e o conteúdo do histórico é um resumo curto de matérias públicas, não um dado pessoal.
- **Fora da regra:** `POST /processar_texto` resume o texto que o próprio usuário envia e não está ligado a uma fonte.
3. **robots.txt:** o de `www.gov.br` (salvo em `tests/fixtures/robots_govbr.txt`) não tem regras para `/aneel` nem `/mme` e não tem `Crawl-delay`; vale a pausa padrão de 1,5 s. Os bloqueios com `?` (`Disallow: /mre/*?`, `/ebserh/*?`) valem só para outros órgãos.
4. **Estrutura:**
   - **ANEEL:** usa Plone Volto. A listagem de notícias é montada por JavaScript e vem vazia no HTML, por isso a descoberta é pelo sitemap do órgão (`/aneel/sitemap.xml.gz`, 2.355 matérias de 2022 a 2026). Na matéria, o corpo não vem como `<p>`: vem nos blocos do objeto `window.__data`, escrito no próprio HTML. O coletor lê esse objeto (`base.extrair_volto`) sem executar JavaScript.
   - **MME:** usa Plone clássico, mas não publica sitemap (404). A descoberta é pela listagem `/mme/pt-br/assuntos/noticias`, paginada com `?b_start:int=N`, que o `robots.txt` permite. A listagem é ampla (petróleo, gás, mineração), por isso só segue os links cujo título passa no filtro de relevância.

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

**Achado analítico.** A correlação de Spearman entre o tempo de isenção e a adoção per capita é de **−0,02** na visão corrigida (−0,06 no critério ANEEL), ou seja, nenhuma relação. Entre as 15 UFs com isenção desde 2015, oito estão abaixo da média nacional de adoção (AL, BA, CE, DF, MA, PE, RJ e SP; no critério ANEEL, também o AC). Entre as que aderiram a partir de 2017, três estão acima (ES, PR e SC). A isenção de ICMS é condição favorável, mas não explica sozinha a disparidade. Correlação não é causalidade, e a amostra tem 27 UFs.

**Modelagem.** A tabela é uma dimensão própria da Gold, unida por `sigla_uf` sob demanda no dashboard e na API. No TP2 o plano era juntá-la ao `gold_uf.csv` dentro do `construir_gold.py`; essa junção foi removida para que atualizar a política não exija reprocessar 4,6 milhões de registros, nem ter a base da ANEEL.

### 2.6 Fatores municipais do potencial solar (TP4.5, Tarefa 3)

**Código:** `src/data_acquisition/coletor_fatores.py` (coleta e registro `FONTES`) e `src/potencial/fatores.py` (montagem) · **Saída:** `data/processed/fatores_municipais.parquet`, 5.570 municípios × 22 colunas.

A tabela reúne os fatores que podem explicar a taxa de realização do potencial solar em telhados. **Regra central:** nenhuma variável é derivada da MMGD, para não vazar o alvo para o modelo. A composição por classe da MMGD fica só como informação descritiva no painel. Nenhum valor ausente é imputado nesta etapa.

|Variável|Fonte e dataset|Ano|Licença|
|---|---|---|---|
|Renda domiciliar per capita, média e mediana (R$/mês)|IBGE, Censo 2022, SIDRA 10295 (variáveis 13431 e 13534)|2022|IBGE: uso livre com citação|
|% da população urbana|IBGE, Censo 2022, SIDRA 9923 (população por situação do domicílio)|2022|IBGE|
|População, log da população, área (km²), densidade (hab/km²)|IBGE, Censo 2022, SIDRA 4714|2022|IBGE|
|% do VAB da agropecuária|IBGE, PIB dos Municípios, base de dados 2010–2023 (FTP)|**2021**|IBGE|
|Tarifa B1 residencial convencional (TE + TUSD, R$/MWh, sem impostos)|ANEEL, Tarifas de aplicação das distribuidoras; média das vigências ponderada pelos dias|2023–2025|ODbL|
|Distribuidoras do município, `multi_distribuidora`|ANEEL, IndQual Município (conjunto → município) + Indicadores de continuidade DEC/FEC 2020–2029 (conjunto → distribuidora)|conjuntos de 2023 em diante|ODbL|
|`cooperativa`, `n_cooperativas`|ANEEL, IASC (classificação concessionária × permissionária), pelo CNPJ|2022–2025|ODbL|
|Ano de início e meses de isenção de ICMS|CONFAZ, Convênio ICMS 16/15 (seção 2.5), por UF|até 31/08/2026|Ato oficial|
|Irradiação (kWh/m²/dia)|NASA POWER, `ALLSKY_SFC_SW_DWN` (TP4.5, Tarefa 1)|2023–2025|Dados abertos da NASA|
|% da área em agropecuária|MapBiomas Brasil, Coleção 11, cobertura e uso da terra por município|2023|CC BY 4.0|
|Região|Cadastro de UFs do projeto (`esquema.py`)|—|—|

**Decisões.**

- **Renda do Censo 2022:** o rendimento domiciliar per capita está publicado em nível municipal (SIDRA 10295) e foi preferido ao PIB per capita.
- **VAB da agropecuária de 2021:** a base do PIB dos Municípios vai de 2010 a 2023, mas a publicação de 2022–2023 (dez/2025) traz só o PIB total e o PIB per capita. Nas linhas de 2022 e 2023 o VAB por atividade está vazio nos 5.570 municípios; o SIDRA 5938 também mostra "..." nesses anos. 2021 é o último ano com o dado. Cachoeira Dourada (GO) tem VAB total negativo no dado oficial (participação de −41,9%), mantido sem tratamento.
- **Distribuidora sem passar pela MMGD:** a ligação vem de bases da ANEEL independentes da MMGD. O arquivo de ligação tem pares geograficamente impossíveis (ex.: Energisa Paraíba em municípios do Maranhão). Uma distribuidora só é ligada a municípios da sua UF principal ou de UFs vizinhas, e 14 pares foram descartados. A MMGD foi usada só para conferência: sua distribuidora principal está na ligação oficial em 99,9% dos municípios.
- **Município com mais de uma distribuidora (567):** tarifa pela média simples, com `multi_distribuidora = True`.
- **Cooperativa:** permissionária de distribuição, isto é, cooperativa de eletrificação regularizada como distribuidora. São 478 municípios com ao menos uma.

**Valores ausentes** (relatório em `data/interim/potencial/fatores_ausentes.csv`): tarifa e variáveis de distribuidora em 10 municípios (0,18%), sem conjunto elétrico atual no arquivo de ligação; área agropecuária em 1 (Fernando de Noronha, fora do MapBiomas); demais variáveis completas.

**Caches da camada Bronze.** Versionados: os três JSONs do SIDRA em `data/raw/ibge/` (`populacao_area_densidade_municipio_2022.json`, 3,2 MB; `populacao_situacao_municipio_2022.json`, 3,3 MB; `renda_domiciliar_pc_municipio_2022.json`, 5,5 MB). Não versionados, por tamanho (cerca de 165 MB no total):

|Arquivo|Tamanho|
|---|---|
|`data/raw/mapbiomas/MAPBIOMAS_BRAZIL-COL.11-BIOME_STATE_MUNICIPALITY.zip`|78,3 MB|
|`data/raw/aneel/indicadores-continuidade-coletivos-2020-2029.parquet`|58,8 MB|
|`data/raw/ibge/pib_municipios/base_de_dados_2010_2023_xlsx.zip`|20,7 MB|
|`data/raw/aneel/indice-aneel-satisfacao-consumidor.csv`|3,3 MB|
|`data/raw/aneel/indqual-municipio.csv`|2,2 MB|
|`data/raw/aneel/tarifas-homologadas-distribuidoras-energia-eletrica.parquet`|1,6 MB|

Para regerá-los (só baixa o que falta no cache) e remontar a tabela:

```bash
python -m src.data_acquisition.coletor_fatores
python -m src.potencial.fatores
```

## 3. Observações sobre Qualidade e Tratamento

- Os dados brutos (ANEEL, IBGE) são armazenados sem alteração em `data/raw/` (camada Bronze) e nunca editados diretamente.
- A limpeza, tipagem, correção e aplicação dos critérios de exclusão ocorre em `data/interim/` (camada Silver), pelo script `src/preparacao/construir_silver.py`. A base é lida e gravada em blocos de 500 mil registros, sem carregar o arquivo completo em memória.
- O dado final, agregado e normalizado por população, fica em `data/processed/` (camada Gold), pelo script `src/preparacao/construir_gold.py`, e alimenta a aplicação.
- A granularidade da ANEEL (registro individual de empreendimento) difere da granularidade do IBGE (população agregada por UF ou município) — a agregação é necessária antes do merge.
- Em leitura por chunks, as colunas são carregadas como texto (`dtype=str`) para evitar inferência de tipo divergente entre blocos. A tipagem é responsabilidade da camada Silver.

### 3.1 Natureza temporal da base e validação do campo de data

O campo `AnmPeriodoReferencia` apresenta **um único valor (10/2026)** em todos os registros (arquivo gerado pela ANEEL em 10/10/2026; a versão anterior do projeto usava a referência 08/2026), indicando que o arquivo é um **retrato da situação corrente** — a relação dos empreendimentos ativos no momento da geração do conjunto de dados — e não uma série histórica de snapshots mensais acumulados.

Em consequência, o único campo temporal disponível para a análise de série histórica é `DthAtualizaCadastralEmpreend`. A nomenclatura do campo sugere tratar-se de data de atualização cadastral, o que levantou a hipótese de que o campo não seria adequado como proxy de adoção — registros atualizados em lote (como na migração do sistema SISGD para o sistema MMGD) poderiam concentrar artificialmente contagens em períodos específicos.

**Validação realizada.** A hipótese foi testada por cruzamento com o painel oficial de Geração Distribuída da ANEEL, disponível em:

> https://app.powerbi.com/view?r=eyJrIjoiY2VmMmUwN2QtYWFiOS00ZDE3LWI3NDMtZDk0NGI4MGU2NTkxIiwidCI6IjQwZDZmOWI4LWVjYTctNDZhMi05MmQ0LWVhNGU5YzAxNzBlMSIsImMiOjR9

Constatou-se que a própria ANEEL utiliza esse campo como **"Ano de conexão"** no painel, e que a distribuição anual de registros obtida localmente **reproduz exatamente** os valores publicados no painel oficial. A verificação foi repetida na base 10/2026 para o Paraná, ano a ano, com diferença de 0,05% na potência (`docs/potencial/atualizacao_base_10_2026.md`, seção 6.2).

**Conclusão.** O campo é adotado como referência temporal de conexão, seguindo a interpretação da própria fonte. A nomenclatura da coluna é enganosa em relação ao seu conteúdo semântico; a evidência do painel oficial prevalece. O cruzamento valida simultaneamente a interpretação do campo e a correção do pipeline de leitura, parsing e agregação implementado no projeto.

**Distribuição anual observada** (`DthAtualizaCadastralEmpreend`, base 10/2026, 4.666.785 registros de todas as fontes, nenhuma data inválida):

|Ano|Registros|Ano|Registros|
|---|---|---|---|
|1900|56|2017|13.098|
|2004|1|2018|35.074|
|2005|1|2019|120.228|
|2009|22|2020|221.726|
|2010|5|2021|449.599|
|2011|39|2022|811.420|
|2012|34|2023|697.096|
|2013|79|2024|915.771|
|2014|270|2025|907.245|
|2015|1.266|2026|487.544|
|2016|6.211|||

A retração observada em 2023 frente a 2022 é consistente com o contexto regulatório descrito no Project Charter: a antecipação de conexões até janeiro de 2023, motivada pela isenção dos custos do Fio B, seguida de arrefecimento e posterior retomada.

### 3.2 Critérios de exclusão de registros

Os seguintes registros são descartados na camada Silver, com o respectivo critério:

|Critério|Registros|Justificativa|
|---|---|---|
|Ano = 1900|56|Data-sentinela; valor de preenchimento sem significado real|
|Ano < 2012|68|A REN nº 482/2012 instituiu o marco regulatório da MMGD; registros anteriores são anomalias cadastrais|
|Potência nula ou ≤ 0|6|Fisicamente inválido para uma usina conectada. Todos os casos no PR, fonte solar, em 2024 e 2025|

**Tratamento do ano corrente (2026):** os dados cobrem apenas parte do ano (referência 10/2026, conexões até o início de outubro). Comparações diretas com anos completos são inválidas. No dashboard, 2026 é sinalizado como período parcial: faixa sombreada no gráfico de evolução e aviso na barra lateral sempre que o ano está dentro do filtro. A coluna `ano_parcial` da camada Gold carrega essa marcação como dado.

**Balanço (base 10/2026):** 4.666.785 registros lidos, 130 descartados, 4.666.655 mantidos na Silver. A conciliação (mantidos + descartados = lidos) é verificada automaticamente a cada execução.

### 3.3 Nota de atualização da fonte

A ANEEL suspendeu temporariamente a atualização dos dados de conexões de MMGD entre 23/09/2025 e 24/10/2025, em razão da migração do sistema SISGD para o novo sistema MMGD. Conexões desse período podem ter sido inseridas retroativamente.

### 3.4 Correções aplicadas na camada Silver

As correções abaixo foram identificadas pelo script `src/preparacao/diagnostico_silver.py`, que investigou os alertas de monitoramento emitidos na primeira execução da camada Silver.

#### 3.4.1 Fonte de geração ausente — imputação como solar

> **Atualização (base 10/2026).** A ANEEL retirou da base os registros do Maranhão sem fonte de geração: o MA passou de 165.020 para 97.458 empreendimentos solares, exatamente o número que o painel oficial já mostrava em agosto (seção 3.6). Restam **156** registros sem fonte, espalhados (PE 64, SC 25, MG 21, RN 12, SP 12, outros 22), de 2021 a 2026, imputados pela mesma regra. Entre os registros com fonte conhecida, 99,98% continuam sendo solares. O texto abaixo documenta a decisão tomada com a base 08/2026.

**Achado (base 08/2026).** 73.501 registros chegavam sem `DscFonteGeracao` e sem `SigTipoGeracao`. A concentração é quase total em uma unidade da federação: 73.352 (99,8%) no Maranhão. O padrão indica falha de preenchimento de uma distribuidora, e não usinas de outra fonte. Não há outro campo da base que permita recuperar a fonte.

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

Na base 08/2026, um registro chegava sem `SigUF` e com código municipal de 6 dígitos (`431780`), quando o padrão do IBGE é de 7. Na base 10/2026 não há ocorrências; a correção permanece no pipeline. O código de 7 dígitos é o de 6 acrescido de um dígito verificador; a correspondência é recuperada pela tabela municipal do IBGE. A UF é derivada do prefixo do código municipal (43 — Rio Grande do Sul).

Na base 10/2026, todos os 4.666.655 registros mantidos têm código municipal de 7 dígitos, com prefixo coerente com o código da UF em 100% dos casos.

#### 3.4.3 Potência suspeita de 75 kW — tratamento aplicado (TP4.5)

**Achado.** Na base 10/2026, 47.190 registros da COPEL-DIS têm potência de exatamente 75 kW, o teto da microgeração, inclusive 28.179 residências, cuja mediana é de 5 kW. A base reproduz o painel oficial da ANEEL (validação ano a ano em 20/11/2026), então a inconsistência está na fonte. Evidências em `docs/potencial/atualizacao_base_10_2026.md`, seção 6.

**Diagnóstico** (`src/preparacao/potencia_suspeita.py`, sem UF ou distribuidora fixada no código). Para cada distribuidora, a fração de residências com exatamente 75 kW. É sinalizada a distribuidora cujo limite inferior do intervalo de Wilson (95%) fica acima de **mediana + 5 × MAD** das frações (0,838%). Só a COPEL-DIS é sinalizada (12,2%). A mesma regra aplicada a todas as classes sinalizava 14 distribuidoras, quase todas cooperativas rurais, onde 75 kW é porte legítimo.

**Tratamento.** Nenhum registro é excluído e a potência oficial (`potencia_kw`) é preservada. Os registros de 75 kW da distribuidora sinalizada recebem `flag_potencia_suspeita` e potência imputada em `potencia_corrigida_kw`: mediana dos registros não sinalizados no primeiro nível com ao menos 5 registros — município + classe + ano (87,8% dos casos), município + classe, distribuidora + classe + ano, UF + classe —, com o nível em `nivel_imputacao_potencia`. `potencia_conservadora_kw` corrige só as residências (limite conservador).

**Impacto.** A potência solar do Brasil passa de 53.788,3 MW (critério ANEEL) para 50.703,6 MW na visão corrigida (51.828,8 MW no limite conservador); a do PR, de 6.862,7 MW para 3.769,9 MW (4.894,3 MW). O painel e a API usam a visão corrigida como padrão e mantêm o seletor "Critério ANEEL", no mesmo padrão da fonte imputada.

### 3.5 Camada Gold

|Tabela|Grão|Conteúdo|Tamanho|
|---|---|---|---|
|`gold_mmgd_agregado.csv`|UF × ano × classe de consumo × fonte imputada|Potência oficial, corrigida e conservadora (kW), quantidade de empreendimentos e de registros com potência suspeita, indicador de ano parcial|109KB|
|`gold_uf.csv`|UF|Nome, região, população (Censo 2022) e, na visão corrigida, potência (MW), watts por habitante, empreendimentos por 100 mil hab., % de registros imputados e % com potência suspeita; potência no critério ANEEL e no limite conservador (MW)|3KB|

**Por que uma tabela no menor grão.** O painel filtra por período, classe de consumo e inclusão de registros imputados. Uma tabela já totalizada por UF impediria recalcular esses recortes. A tabela agregada guarda o menor nível que o painel precisa e a aplicação soma depois de filtrar. O mesmo vale para a potência acumulada, calculada na aplicação.

**Métricas per capita.** Watts por habitante é a métrica principal: ordem de grandeza legível e unidade usual no setor. Empreendimentos por 100 mil habitantes a complementa — potência mede volume investido, contagem mede difusão.

**Escopo.** Apenas fonte solar, incluindo os registros imputados, marcados pela coluna `fonte_imputada`. A visão corrigida (padrão) usa `potencia_corrigida_kw`; o critério ANEEL exclui os imputados e usa a potência oficial.

### 3.6 Validação contra o painel oficial da ANEEL

> **Atualização (base 10/2026).** A base 10/2026 resolve as duas questões abertas abaixo. O Maranhão tem 97.458 empreendimentos solares, **o mesmo número do painel de agosto**: os registros sem fonte foram retirados da própria base, e a conclusão de que o painel subestimaria o MA não se sustenta. A potência solar total (53.802,8 MW) fica 0,3% acima da que o painel mostrava em agosto (53.650,9 MW), e a contagem (4.665.900), 0,2% acima: a divergência de 6,3% vinha do arquivo de 08/2026, defasado em relação ao painel. Uma nova validação ano a ano, feita em 20/11/2026 para o Paraná, reproduziu o painel com diferença de 0,05% na potência e revelou a anomalia dos registros de 75 kW, tratada na seção 3.4.3. A tabela abaixo documenta a validação feita com a base 08/2026.

O resultado da camada Gold (base 08/2026) foi comparado com o painel oficial de Geração Distribuída da ANEEL (dados até 31/08/2026). O arquivo processado foi gerado pela ANEEL em 19 de Agosto de 2026.

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

**Resultado (base 10/2026, visão corrigida).** O parque solar distribuído passou de 9,6 GW (2021) para 17,7 GW (2022), 26,3 GW (2023), 36,8 GW (2024) e 46,3 GW (2025), chegando a 50,7 GW até outubro de 2026. O crescimento anual desacelera: 85,4%, 48,5%, 40,0% e 25,6%. O CAGR de 2022 a 2025 é de **37,7% ao ano** (37,5% na base 08/2026).

**Critério ANEEL.** Com a potência oficial, inflada pelos registros de 75 kW do Paraná em 2019–2022, o parque vai de 20,2 GW (2022) a 49,2 GW (2025) e 53,8 GW em outubro de 2026, e o CAGR cai para 34,6%. No limite conservador, 36,9%.

### 3.8 Matriz de oportunidade

Cruza a adoção per capita (W/hab acumulado até outubro de 2026) com o crescimento do parque (CAGR 2022–2025). As referências são nacionais: 249,7 W/hab (total do país ÷ população, e não média simples das UFs) e 37,7% ao ano, na visão corrigida (264,9 W/hab e 34,6% no critério ANEEL).

|Quadrante|Leitura|UFs (visão corrigida, base 10/2026)|
|---|---|---|
|Líder em expansão|Adoção e crescimento acima da referência|AC, ES, GO, MS, MT, PI, RN, RO, TO|
|Mercado maduro|Adoção acima, crescimento abaixo|MG, PR, RS, SC|
|**Mercado emergente**|Adoção abaixo, crescimento acima — **o próximo mercado solar**|AL, AP, BA, CE, MA, PA, PE, RR, SE, SP|
|**Lacuna persistente**|Adoção e crescimento abaixo — **foco de política pública (ODS 10)**|AM, DF, PB, RJ|

**Mudanças em relação à base 08/2026.** AP e MA deixam "líder em expansão" e AM vai para "lacuna persistente", por alteração dos próprios registros na fonte. O AC passa a "líder em expansão": sua adoção (250,0 W/hab) fica logo acima da nova referência. **No critério ANEEL**, a anomalia dos 75 kW infla as referências nacionais (264,9 W/hab e 34,6%), e RJ e AC aparecem como "mercado emergente"; esse resultado é artefato da anomalia. Detalhes em `docs/potencial/atualizacao_base_10_2026.md`, seções 5 e 6.3.

**Sensibilidade à correção do Maranhão.** Na base 08/2026, a imputação dos registros sem fonte mudava a classificação do MA: "líder em expansão" na visão corrigida, "lacuna persistente" no critério ANEEL. Na base 10/2026 esses registros não existem mais, e o MA é "mercado emergente" (163,6 W/hab) nas duas visões. As duas visões continuam no dashboard e na API; quanto à fonte, agora diferem em apenas 156 registros, e a diferença principal passou a ser a potência corrigida dos registros de 75 kW (seção 3.4.3).

**Ressalva.** UFs com parque pequeno em 2022 tendem a exibir taxas altas; o caso extremo é o AP, com 90,9% ao ano. O tamanho do círculo no gráfico (potência absoluta) e a ficha da UF na API (`/ufs/{sigla}`, com os parques inicial e final) tornam isso visível.

### 3.9 Pendências

|Item|Situação|
|---|---|
|Classe de consumo `REBR`|47.844 registros em 14 UFs (base 10/2026), sem significado documentado. Mantida sem alteração até consulta ao dicionário de dados da ANEEL|
|Divergência de potência com o painel oficial|Resolvida com a base 10/2026 (seção 3.6)|
|Registros de 75 kW no Paraná|**Tratamento aplicado** (seção 3.4.3): sinalização por diagnóstico entre distribuidoras e imputação da potência na visão corrigida. Resta registrar a inconsistência junto à ANEEL e rever a regra se a base mudar (a margem da segunda distribuidora é estreita)|
|Agência Gov pelo sitemap|Coleta feita em 20/11/2026 (seção 2.3). O sitemap cobre sobretudo os meses recentes; matérias antigas só entram se aparecerem nele ou na editoria Energia|
|~~Resumo das fontes CC BY-ND~~|**Resolvida em 22/11/2026:** sem resumo para ANEEL, MME e Agência Gov (seção 2.4)|
|~~Relevância das notícias da ANEEL e do MME~~|**Resolvida em 22/11/2026:** o corpus inteiro (553) foi reprocessado com a estratégia híbrida adotada no benchmark v2 (seção 5.2)|
|Novo conjunto de teste rotulado|O teste congelado do benchmark v2 já foi consultado duas vezes (seção 5.2). Confirmar a estratégia híbrida exige um conjunto novo, nunca consultado|
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

São 16 rotas em `src/api/` (13 do TP3 e 3 de IA do TP4, seção 5), documentadas em `docs/api.md` e em `/docs` (Swagger). Todas as respostas usam modelos Pydantic (`response_model`). Os erros seguem um formato único (`{"detail": ...}`):

- **400** filtros incoerentes;
- **404** recurso inexistente;
- **409** notícia duplicada;
- **422** validação dos dados enviados;
- **503** dados indisponíveis ou modelo de linguagem não pronto;
- **504** inferência acima do tempo limite;
- **500** erro inesperado, registrado no log, sem rastro de pilha para o cliente.

As duas rotas de envio são:

- `POST /noticias`: valida URL, tamanhos e data (entre 2012 e hoje), recusa URLs repetidas e detecta as UFs. Grava em `data/external/noticias_enviadas.csv`, arquivo separado do corpus coletado para que uma nova raspagem não sobrescreva as contribuições.
- `POST /comparacoes`: recebe um indicador por UF e devolve posições, diferença de posições e correlação de Spearman com a adoção. É a versão em API do upload da página Dados.

### 4.4 Testes

São 104 testes automatizados (`python -m pytest`):

- **Serviços:** reprodução exata do `gold_uf.csv`, filtros, monotonia do parque, CAGR e quadrantes.
- **API:** todas as rotas e todos os códigos de erro.
- **Scrapers:** extração das duas fontes, `robots.txt` bloqueando, cache, RSS sem texto integral e preservação de `resumo`/`sentimento` na mescla.
- **ICMS:** datas por UF, inferências e § 3º.
- **Gold:** execução com Silver sintética.
- **Upload.**
- **Dashboard:** todas as páginas via `AppTest` e persistência dos filtros.
- **IA (TP4):** métricas, catálogo, estados do gerenciador de modelos, rotas de IA com todos os erros, processamento em lote incremental e inferência real com modelos minúsculos criados na hora (mesma arquitetura T5 e DeBERTa, sem download).

Também foi executado um teste de integração real, com a API no uvicorn e a página API do dashboard enviando uma notícia por HTTP: a resposta foi 201 e o reenvio, 409.

## 5. Modelos de Linguagem Locais (TP4)

### 5.1 Tarefas e modelos

O corpus de notícias é processado por modelos executados localmente (HuggingFace Transformers e PyTorch), escolhidos por benchmark. A justificativa completa, com os resultados de cada candidato, está em `docs/escolha_modelo.md`.

|Tarefa|Modelo|Resultado no benchmark|Uso|
|---|---|---|---|
|Resumo|`recogna-nlp/ptt5-base-summ` (MIT)|ROUGE-1 0,344, contra 0,309 do início do texto|Gravado no corpus; página Notícias e API|
|Relevância|`MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` (MIT), zero-shot|F1 macro 0,71, contra 0,43 de "sempre relevante"|Gravada no corpus; filtro na página Notícias e em `GET /noticias`|
|Tom|mesmo mDeBERTa|Acurácia 0,43, contra 0,83 de "sempre favorável"|**Reprovado**: só na API, como experimental|

### 5.2 Dados do benchmark

|Conjunto|Origem|Tamanho|Uso|
|---|---|---|---|
|`docs/benchmark/rotulos_benchmark.csv`|Amostra estratificada por fonte e período (`src/ia/rotulagem.py`), rotulada manualmente pela autora seguindo `docs/benchmark/README.md`|30 notícias: 23 relevantes, 7 fora do tema; entre as relevantes, 19 favoráveis, 2 desfavoráveis e 2 neutras|Gabarito de relevância e tom|
|Linhas finas próprias|Corpus: notícias cuja linha fina não repete o primeiro parágrafo|56 notícias|Referência de resumo (o modelo recebe a notícia **sem** a linha fina, para não haver vazamento)|

Achado de qualidade do corpus: em 56 das 119 notícias, a "linha fina" coletada é o primeiro parágrafo da matéria (o portal repete o lide na meta descrição). A entrada do modelo (`texto_para_modelo`) passou a omitir a linha fina nesses casos, para não gastar a janela de 512 tokens com texto duplicado.

**Decisão: sem notícias sintéticas (20/11/2026).** Foi avaliado gerar notícias sintéticas para ampliar os dados de IA, e a ideia foi descartada. Nenhum modelo do projeto é treinado com dados do projeto: a relevância e o tom são classificados em zero-shot (mDeBERTa NLI), e o resumo usa um PTT5 já ajustado pelos autores. Sem treino, texto sintético não teria uso, e num gabarito de avaliação ele mediria o modelo contra textos escritos já com o rótulo em mente. A melhoria segue dois caminhos com dados reais:
- a ampliação do benchmark com notícias novas, rotuladas pela autora com o mesmo guia (`src/ia/rotulagem.py --v2`);
- a engenharia da hipótese de relevância, que hoje fala só em "energia solar" e falha em notícias de geração distribuída que não usam essa palavra (seção 5.4).

**Planilha do benchmark v2 (20/11/2026).** `docs/benchmark/rotulos_benchmark_v2_pendentes.csv` tem **120 notícias reais**, com rótulos vazios para a autora preencher: ANEEL 74, MME 23, Agência Brasil 21 e Agência Gov 2. Elas foram sorteadas, com semente fixa, entre as 525 notícias do corpus que estão fora do gabarito v1. Ficaram de fora também as 2 notícias do v1 descobertas por caminho proibido que não voltaram pelo sitemap (seção 2.3). Entre as 120, **33 são de GD sem "solar"** (30 da ANEEL e 3 do MME): 20 entram pela cota reservada a esse caso, e as demais vieram do sorteio estratificado por fonte e palavra-chave.

**Benchmark v2 (22/11/2026).** A autora rotulou as 120 notícias da planilha. Junto com o v1, sem as 2 notícias fora do v2, o gabarito ficou com 148 notícias, divididas em desenvolvimento (59) e teste congelado (89). A divisão foi estratificada por rótulo, fonte e GD sem "solar", com semente fixa (`src/ia/benchmark_relevancia.py`). O subconjunto GD sem "solar" é 23% do gabarito e 14% do corpus: a sobre-representação é proposital. Resultado da primeira consulta ao teste (detalhes em `docs/escolha_modelo.md`, seção 9):

- **Relevância.** A estratégia escolhida no desenvolvimento (máximo de três hipóteses curtas) superou a atual no F1 da classe "sim" (0,834 contra 0,712; diferença +0,123, IC 95% [0,035; 0,208]). Mas empatou com responder sempre "sim" (0,837; diferença −0,002, IC 95% [−0,022; 0,016]) e por isso não foi adotada. A configuração atual continua no catálogo e erra todas as 12 notícias relevantes de GD sem "solar" do teste.
- **Tom.** O F1 macro foi de 0,248, contra 0,286 da linha de base de classe majoritária. Continua reprovado.
- **Resumo.** O benchmark de resumo não foi reexecutado. Com o corpus de 553 notícias, a amostra seria de **356 notícias**, contra 56.

**Correção de métrica e segunda consulta ao teste (22/11/2026).** O critério da primeira escolha, F1 da classe "sim", estava errado para este corpus: com 72% de relevantes, "sempre sim" vence quase automaticamente. A escolha foi refeita só no desenvolvimento, pelo **F1 macro**, com as probabilidades já salvas e sem nova inferência. As restrições foram superar "sempre sim" e ter F1 maior que zero em GD sem "solar". A escolha caiu no **híbrido**: a notícia é relevante se o título cita um termo de geração distribuída OU se a hipótese "Esta notícia trata de energia solar." passa de 0,4.

Na **segunda consulta** ao teste congelado, o F1 macro foi 0,678 [IC 95% 0,572; 0,783]. A configuração anterior teve 0,573 e "sempre sim", 0,418, com as duas diferenças pareadas acima de zero. No subconjunto GD sem "solar", foi 0,903, contra 0,300. A estratégia foi adotada em `src/ia/catalogo.py`. Por ser a segunda consulta, feita depois de corrigir a métrica, a evidência é mais fraca que a de uma consulta única, e um novo conjunto de teste ficou como pendência (seção 3.9). A primeira avaliação continua em `resultado_teste_congelado.json` e a segunda está em `resultado_teste_congelado_v2.json`.

**Reprocessamento do corpus.** As 553 notícias foram reprocessadas com a nova estratégia:

- **Relevância:** 399 julgadas relevantes (72%). Em 71 delas, foi a regra de palavra do título que decidiu (coluna `relevancia_por_termo`): ANEEL 36, MME 33, Agência Brasil 1 e Agência Gov 1.
- **Resumo:** só as 134 notícias da Agência Brasil têm resumo, idênticos aos anteriores. As fontes do gov.br ficaram sem resumo (seção 2.4).
- **Rastreio da configuração:** `modelo_relevancia` passou a registrar o modelo e a estratégia (`… | hibrido_titulo@0.4`), para que uma troca futura torne as notícias pendentes de novo.

### 5.3 Processamento em lote e armazenamento

`python -m src.ia.processar_corpus` resume e avalia a relevância de cada notícia e grava `data/processed/corpus_ia.csv`:

|Coluna|Conteúdo|
|---|---|
|`id`|Chave de ligação com `corpus_noticias.csv`|
|`resumo`, `resumo_truncado`|Resumo gerado e se a notícia passou do limite de 512 tokens|
|`relevante`, `relevancia_prob`|Julgamento do modelo e probabilidade (limiar 0,5)|
|`modelo_resumo`, `modelo_relevancia`|Identificador de cada modelo no HuggingFace Hub (rastreabilidade)|
|`processado_em`|Data e hora do processamento|

**Por que um arquivo separado.** O corpus é escrito pelos coletores e o enriquecimento por outro processo. Separados, uma nova coleta não apaga o que já foi processado e um novo processamento não regrava o corpus. A carga (`servicos/dados.py`) junta os dois pelo `id`; notícias ainda não processadas ficam com relevância nula ("não avaliada"), nunca "irrelevante".

**Incremental.** O lote só processa notícias sem resultado do par de modelos atual. Trocar de modelo reprocessa tudo, e as colunas `modelo_*` registram qual modelo gerou cada linha.

**Versionado no Git.** O painel e a API mostram resumo e relevância em qualquer máquina, sem GPU e sem baixar os modelos (~2 GB).

### 5.4 Limitações dos dados gerados

- **Truncamento:** 64% das notícias passam do limite no resumo e 80% na classificação. O modelo lê o início, onde o texto jornalístico concentra o essencial.
- **Resumo não é fonte:** resumos automáticos podem omitir ou distorcer detalhes. O painel sempre mostra o link da matéria original ao lado, e o resumo nunca alimenta um indicador numérico.
- **Relevância mais estrita que a rotulagem:** quatro dos cinco falsos negativos do benchmark são notícias sobre renováveis em geral. O filtro tende a excluir esse tipo de notícia. No lote de 16/11/2026, 28 das 119 notícias foram julgadas fora do tema, e entre elas havia notícias de geração distribuída que não mencionam "solar". Desde 22/11/2026, a estratégia híbrida (termo de GD no título OU zero-shot) cobre esse caso (seção 5.2). GD citada só no corpo ainda depende do modelo, e o filtro do painel continua desligado por padrão.
- **Licença:** resumos são obras derivadas. Só a Agência Brasil recebe resumo, e cada resumo mantém a ligação com a URL de origem. As fontes sob CC BY-ND (ANEEL, MME e Agência Gov) não recebem resumo (seção 2.4).

## 5A. Agente de Decisão (TP5)

O agente é a última camada do ciclo de dados: transforma a Gold de todas as etapas em respostas para gestão e investimento. Metodologia completa em `docs/agente/README.md`.

### 5A.1 Como cada dado coletado chega ao agente

|Dado (etapa)|Coleta|Tratamento|Ferramenta do agente|
|---|---|---|---|
|MMGD da ANEEL (TP1–TP4.5)|API de dados abertos (CKAN), download em streaming|Silver/Gold, três visões dos 75 kW|`resumo_potencial`, `adocao_uf`, `comparar_ufs`, `oportunidades`|
|População e domicílios, IBGE (TP1, TP4.5)|API de Agregados v3 (SIDRA)|Gold municipal, peso do potencial|`resumo_potencial`, `adocao_uf`|
|Irradiação NASA POWER (TP4.5)|API REST, ponto por município|média 2023–2025|`resumo_potencial`, `explicar_gap`|
|Fatores municipais (TP4.5)|SIDRA, PIB dos Municípios, tarifas ANEEL, MapBiomas|`fatores_municipais.parquet`|`explicar_gap` (valores e mediana)|
|Modelo explicativo e SHAP (TP4.5)|—|LightGBM, validação agrupada por UF|`explicar_gap`, `oportunidades` (taxa prevista)|
|NEX-GDDP-CMIP6 (TP4.5)|leitura parcial do bucket público da AWS|método delta, 5 modelos|`cenarios_climaticos`|
|CONFAZ, Convênio ICMS 16/15 (TP3)|web scraping (BeautifulSoup), com robots.txt|`gold_icms_uf.csv`|`politica_icms`|
|Notícias EBC e gov.br (TP2–TP4)|web scraping multifonte|relevância (mDeBERTa) e resumo (PTT5)|`noticias` (só relevantes; resumo só onde a licença permite)|

### 5A.2 Dados gerados pelo agente

- **Gap acima do esperado** (`ferramentas.tabela_oportunidades`): `max(0, taxa prevista − observada) × potencial`, calculado na hora a partir de `shap_municipal.parquet` e `potencial_municipal.parquet`. Não é gravado na Gold, para não duplicar dado derivável.
- **Respostas do agente:** não são gravadas pelo servidor. A conversa fica na sessão do navegador e pode ser baixada pelo usuário (.md).
- **Avaliação:** `docs/agente/avaliacao_regras.csv` e `avaliacao_llm.csv`, com 15 perguntas de gabarito.

### 5A.3 Qualidade e limites dos dados no agente

- **Verificação de números:** toda resposta passa por `verificacao.py`. Número que não está nos fatos consultados gera aviso visível ao usuário.
- **Visões:** o agente segue o seletor de visão. Nas visões ANEEL e conservadora, as contribuições SHAP continuam as do modelo treinado na visão corrigida, com aviso explícito (mesma regra da página Potencial Solar).
- **Privacidade:** o agente só lê a Gold agregada por município, sem dado pessoal. Com o provedor padrão (Ollama), nada sai da máquina. Com um provedor online, só os fatos agregados e a pergunta são enviados.

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
|`corpus_noticias.csv`|< 1 MB|✅ Sim|Corpus para o dashboard, a API e os modelos de linguagem|
|`corpus_ia.csv`|< 100 KB|✅ Sim|Resumo e relevância gerados em lote (TP4); dispensa GPU e download dos modelos para avaliar|
|`docs/benchmark/`|< 200 KB|✅ Sim|Rótulos manuais, saídas e métricas do benchmark: evidência da escolha dos modelos|
|Pesos dos modelos (cache do HuggingFace)|~2 GB|❌ Não|Baixados automaticamente na primeira carga|
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
- **TP4 (concluído):**
  - benchmark de cinco modelos no próprio corpus, com rotulagem manual (`docs/escolha_modelo.md`);
  - resumo (PTT5) e relevância (mDeBERTa) do corpus em lote, versionados em `corpus_ia.csv`;
  - rotas `POST /processar_texto`, `POST /noticias/{id}/processar` e `GET /ia/status`, com modelos de resposta e erros 422, 503 e 504;
  - página Laboratório de IA e resumo/relevância na página Notícias;
  - tom reprovado no benchmark e mantido só como experimental.
- **Pendências herdadas para o TP5:**
  - ~~atualizar a base da ANEEL para a referência 10/2026~~ — concluído em 20/11/2026 (`docs/potencial/atualizacao_base_10_2026.md`), com tratamento aplicado aos registros de 75 kW do Paraná (seção 3.4.3);
  - ampliar o corpus (Agência Senado, Agência Câmara e agências estaduais), com verificação de termos de uso fonte a fonte.
- **TP5 (concluído):**
  - agente inteligente de apoio à decisão (seção 5A), que usa a camada de serviços da API como ferramentas e lê só as notícias relevantes e já resumidas;
  - página *Agente de decisão* no painel e rotas `/agente` na API;
  - 472 testes automatizados.
- **Depois do TP5:**
  - reavaliar o tom das notícias com um LLM, contra os mesmos 30 rótulos (planejado para o TP5, não realizado: o foco foi o agente);
  - revisar as regras de ação do agente com profissionais do setor solar;
  - unificar o parâmetro `visao` nas rotas de indicadores (pendência registrada em `docs/api.md`).
