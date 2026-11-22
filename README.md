# ☀️ SolarGap Brasil

### Onde está o próximo mercado solar?

Mapeamento da desigualdade regional na adoção de energia solar distribuída no Brasil, a partir de dados abertos da ANEEL e do IBGE.

O projeto quantifica a disparidade entre unidades da federação na adoção de micro e minigeração distribuída (MMGD), normalizada pela população — revelando tanto os estados que ficam para trás na transição energética quanto os mercados ainda inexplorados pelo setor solar.

**Objetivos de Desenvolvimento Sustentável:** ODS 7 (Energia Limpa e Acessível) · ODS 10 (Redução das Desigualdades)

---

## 📋 Sobre o projeto

Desde a Lei nº 14.300/2022 — o Marco Legal da Geração Distribuída — a energia solar distribuída se expandiu de forma acelerada no Brasil, mas não de maneira homogênea entre os estados. Este projeto mapeia e quantifica essas assimetrias por meio de um painel interativo e de uma API.

Documentação completa:

- 📄 [Project Charter](docs/project_charter_solargap.docx) — escopo, objetivos, KPIs, stakeholders e cronograma
- 📊 [Data Summary Report](docs/data_summary_report.md) — fontes, qualidade, tratamento e licenciamento dos dados
- 🔌 [Documentação da API](docs/api.md) — rotas, parâmetros, exemplos e códigos de erro
- 🧠 [Escolha dos modelos de linguagem](docs/escolha_modelo.md) — benchmark de cinco modelos locais (TP4)
- 🔄 [Atualização da base ANEEL 08/2026 → 10/2026](docs/potencial/atualizacao_base_10_2026.md) — antes × depois e tratamento dos 75 kW no PR
- 🏠 [Potencial solar municipal](docs/potencial/README.md) — potencial x produção, fatores (SHAP), validação e projeção 2030–2050 (TP4.5)

### Indicadores

| KPI | Definição |
|---|---|
| Watts por habitante | Potência solar instalada dividida pela população (Censo 2022), por estado |
| Empreendimentos por 100 mil hab. | Difusão: sistemas conectados para cada 100 mil habitantes |
| Ranking de disparidade | Posição das 27 UFs em cada métrica, com a média nacional como referência |
| Taxa de crescimento | Crescimento anual do parque instalado e CAGR por UF desde a Lei 14.300 (2022–2025) |
| Taxa de realização (TP4.5) | Produção estimada da MMGD residencial e rural (y) sobre o potencial técnico dos telhados residenciais (x), por município e UF; gap = x − y |

### Principais achados (base ANEEL 10/2026, visão corrigida)

Valores na visão corrigida, padrão do painel; entre parênteses, o critério ANEEL (dado oficial sem correções).

- O parque solar distribuído passou de 17,7 GW (2022) para 46,3 GW (2025): **37,7% ao ano** (34,6%), chegando a 50,7 GW até outubro de 2026 (53,8 GW). O ritmo desacelera (48,5% em 2023, 25,6% em 2025).
- **10 "mercados emergentes"** — adoção abaixo da média nacional, crescimento acima: AL, AP, BA, CE, MA, PA, PE, RR, SE e SP (no critério ANEEL, também AC e RJ).
- **4 "lacunas persistentes"** — adoção e crescimento abaixo da média: AM, DF, PB e RJ (no critério ANEEL, só AM, DF e PB).
- **Tratamento aplicado à anomalia dos 75 kW:** 47 mil registros da COPEL-DIS no Paraná, inclusive 28 mil residências, têm potência de exatamente 75 kW, o teto da microgeração. A base reproduz o painel oficial da ANEEL, então o erro está na fonte. O pipeline sinaliza esses registros por diagnóstico estatístico entre distribuidoras e imputa a potência mediana de sistemas semelhantes: a potência solar do PR cai de 6,9 para 3,8 GW e a do Brasil, de 53,8 para 50,7 GW. Detalhes em [`docs/potencial/atualizacao_base_10_2026.md`](docs/potencial/atualizacao_base_10_2026.md).
- Na base de 10/2026, a ANEEL retirou os ~73 mil registros do Maranhão sem fonte de geração, que o projeto imputava como solares. O MA passou a ser "mercado emergente" nas duas visões do painel.
- O momento de adesão à isenção de ICMS (Convênio 16/15) não se relaciona com a adoção atual (Spearman −0,02; −0,06 no critério ANEEL).
- **Potencial solar residencial (TP4.5):** os telhados residenciais poderiam gerar 302,6 TWh/ano; a micro e minigeração residencial e rural produz cerca de 31,5 TWh/ano, ou **10,4% do potencial** (11,4% no critério ANEEL; 10,6% no limite conservador). A taxa está associada sobretudo à densidade demográfica (municípios densos aproveitam menos) e à renda (associação, não causalidade). Até 2050, a irradiação muda poucos por cento nos cenários climáticos, com faixa de incerteza que cruza o zero na maioria das UFs. Detalhes em [`docs/potencial/README.md`](docs/potencial/README.md).

---

## 🗂️ Fontes de dados

| Fonte | Conteúdo | Acesso |
|---|---|---|
| ANEEL — Relação de Empreendimentos de Geração Distribuída | ~4,7 milhões de registros de empreendimentos MMGD | Portal de Dados Abertos (CKAN) |
| IBGE — Censo Demográfico 2022 | População residente por UF e por município | API de Agregados v3, tabela 9923 |
| Agência Brasil (EBC) | Notícias sobre energia solar (texto integral) | Web scraping (BeautifulSoup) |
| Agência Gov (EBC) | Notícias do governo federal, incluindo boletins da ANEEL (texto integral) | Web scraping (BeautifulSoup) — nova no TP3 |
| CONFAZ — Convênio ICMS 16/15 | Adesão das 27 UFs à isenção de ICMS na geração distribuída | Texto oficial, BeautifulSoup + parser — nova no TP3 |

Detalhamento, avaliação das fontes descartadas e licenças em [`docs/data_summary_report.md`](docs/data_summary_report.md).

---

## 📁 Estrutura do projeto

```
solargap-brasil/
├── data/
│   ├── raw/                      # 🥉 Bronze — dados originais e cache HTML (parcialmente versionado)
│   ├── interim/                  # 🥈 Silver — limpos e tipados (não versionado)
│   ├── processed/                # 🥇 Gold — agregados, prontos para app e API
│   └── external/                 # referências de terceiros curadas (Convênio ICMS 16/15, malhas do IBGE)
├── docs/
│   ├── project_charter_solargap.docx
│   ├── data_summary_report.md
│   ├── api.md
│   ├── escolha_modelo.md         # justificativa dos modelos de linguagem (TP4)
│   ├── potencial/                # potencial solar municipal: método, SHAP, cenários (TP4.5)
│   └── benchmark/                # rótulos manuais, saídas e métricas do benchmark (TP4)
├── src/
│   ├── data_acquisition/
│   │   ├── coletor_base.py       # infraestrutura compartilhada (retry, logging, paths)
│   │   ├── aneel.py              # download em streaming da base MMGD
│   │   ├── ibge.py               # coleta populacional (UF e município)
│   │   ├── icms_confaz.py        # adesão ao Convênio ICMS 16/15 (TP3)
│   │   └── noticias/             # scrapers de notícias multifonte (TP3)
│   │       ├── base.py           #   robots.txt, pausa, retry, extração independente de layout
│   │       ├── fontes.py         #   fontes avaliadas, licenças e justificativas
│   │       └── coletor.py        #   orquestração e mescla incremental do corpus
│   ├── preparacao/
│   │   ├── esquema.py            # constantes compartilhadas e contrato do corpus
│   │   ├── construir_silver.py   # camada Silver
│   │   ├── construir_gold.py     # camada Gold
│   │   └── ...                   # amostra e diagnósticos
│   ├── servicos/                 # regra de negócio usada pelo app E pela API (TP3; potencial.py no TP4.5)
│   ├── potencial/                # pipeline do potencial solar: x, y, fatores, SHAP, CMIP6 (TP4.5)
│   ├── ia/                       # modelos de linguagem locais (TP4)
│   │   ├── catalogo.py           #   candidatos, modelo de cada tarefa, hipóteses zero-shot
│   │   ├── modelos_hf.py         #   carga e inferência (único módulo que importa torch)
│   │   ├── motor.py              #   carga única, estados, fila de inferência
│   │   ├── benchmark.py          #   comparação dos candidatos (qualidade, tempo, memória)
│   │   └── processar_corpus.py   #   resumo e relevância do corpus em lote
│   ├── api/                      # API FastAPI (TP3)
│   │   ├── main.py               #   aplicação e tratamento de erros
│   │   ├── modelos.py            #   modelos Pydantic de entrada e resposta
│   │   └── rotas/                #   sistema, indicadores, potencial, notícias, políticas, comparações, ia
│   └── app/                      # dashboard Streamlit multipáginas (TP3)
│       ├── app.py                #   entrada: menu, seletor de visão (todas as páginas) e filtros
│       └── paginas/              #   Início, Panorama, Evolução, Oportunidades, Potencial Solar, Notícias, Laboratório de IA, Dados, API
├── tests/                        # 402 testes automatizados (pytest)
├── requirements.txt
├── setup_project.py
└── README.md
```

### Arquitetura

```
 Fontes ──> data_acquisition ──> Bronze ──> Silver ──> Gold ──┐
                                                              ├──> servicos ──┬──> app (Streamlit)
 data/external (referências) ─────────────────────────────────┘               └──> api (FastAPI) ──> TP5: agente
```

| Camada | Diretório | Conteúdo | Versionado |
|---|---|---|---|
| 🥉 Bronze | `data/raw/` | Cópia fiel da fonte, nunca editada | Parcial¹ |
| 🥈 Silver | `data/interim/` | Limpo, tipado, ainda granular | ❌ Reproduzível |
| 🥇 Gold | `data/processed/` | Agregado e normalizado, consumido pelo app e pela API | ✅ Sim |
| Externa | `data/external/` | Referências curadas com fonte documentada | ✅ Sim² |

¹ Os arquivos do IBGE e a amostra estratificada da ANEEL são versionados. A base completa da ANEEL e o cache HTML dos scrapers **não são**.
² Exceto `noticias_enviadas.csv`, gravado pela API em tempo de execução.

---

## 🚀 Como rodar

**Pré-requisitos:** Python 3.11 ou superior.

```bash
# 1. Clonar o repositório
git clone https://github.com/pziliotto/solargap-brasil.git
cd solargap-brasil

# 2. Criar e ativar o ambiente virtual
python -m venv .venv
# Windows (PowerShell)
.\.venv\Scripts\Activate
# Linux / macOS
source .venv/bin/activate

# 3. Instalar as dependências
#    Com GPU NVIDIA: instale o PyTorch com CUDA ANTES, senão o pip baixa a versão só-CPU
pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cu132
pip install -r requirements.txt
```

O PyTorch 2.15 com CUDA 13.2 exige driver NVIDIA recente (`nvidia-smi` deve mostrar "CUDA Version" 13.2 ou maior). Sem GPU, basta o `pip install -r requirements.txt`: os modelos rodam em CPU, mais devagar.

**Dashboard** (a partir da raiz):

```bash
python -m streamlit run src/app/app.py
```

**API** (em outro terminal, a partir da raiz):

```bash
uvicorn src.api.main:app --reload
# Documentação interativa: http://127.0.0.1:8000/docs
```

**Visão dos dados.** O seletor da barra lateral vale para todas as páginas: **visão corrigida** (padrão; imputa a potência dos registros de 75 kW da COPEL-DIS e conta como solares os 156 registros sem fonte), **critério ANEEL** (dado oficial) e **limite conservador** (corrige só os residenciais de 75 kW). Na API, as rotas `/potencial` recebem o parâmetro `visao`; as de indicadores, `incluir_imputados`. Ver [`docs/api.md`](docs/api.md).

O dashboard funciona sem a API; as páginas **API** e **Laboratório de IA** usam a API quando ela está no ar. Na primeira execução, a API baixa os modelos de linguagem (~2 GB) para o cache do HuggingFace; enquanto carregam, as rotas de IA respondem 503 e o resto funciona normalmente. Para subir a API sem os modelos: `SOLARGAP_CARREGAR_MODELOS=0`.

**Modelos de linguagem (opcional — os resultados já estão versionados):**

```bash
python -m src.ia.processar_corpus      # resumo e relevância das notícias pendentes
python -m src.ia.benchmark             # repete a comparação dos modelos
```

**Testes:**

```bash
python -m pytest
```

A aplicação funciona imediatamente após o clone, usando a camada Gold versionada — **não é necessário baixar a base completa** para avaliar o projeto.

### Coleta de dados (opcional)

```bash
python -m src.data_acquisition.ibge             # população por UF e município
python -m src.data_acquisition.aneel            # base MMGD completa (~105 MB)
python -m src.data_acquisition.noticias         # notícias (fontes habilitadas)
python -m src.data_acquisition.noticias --listar  # situação de cada fonte
python -m src.data_acquisition.icms_confaz      # adesão ao Convênio ICMS 16/15
python -m src.preparacao.construir_silver       # camada Silver
python -m src.preparacao.construir_gold         # camada Gold
```

> ⚠️ **Os scripts devem ser executados a partir da raiz do projeto**, com a sintaxe `python -m pacote.modulo` (pontos, sem `.py`). Executá-los diretamente provoca `ModuleNotFoundError`.

---

## ⚠️ Limitações conhecidas

**Restrição geográfica da ANEEL.** O Portal de Dados Abertos da ANEEL aplica filtragem por IP de origem; fora do Brasil é necessária VPN com saída no Brasil. Não afeta a avaliação: a camada Gold está versionada.

**robots.txt do CONFAZ.** Na avaliação do TP3 o acesso automatizado ao CONFAZ foi bloqueado. O coletor respeita o robots.txt a cada execução e, se bloqueado, usa a cópia de referência do texto oficial em `data/external/confaz/` (ato oficial, sem proteção autoral — Lei 9.610/98, art. 8º, IV).

**Fontes de notícias.** Veículos privados avaliados (g1, CNN Brasil, R7, CanalEnergia, MegaWhat, eixos) não foram incluídos por termos de uso ou paywall. O motivo de cada um está em `src/data_acquisition/noticias/fontes.py`.

**Dados pessoais excluídos na origem.** `NumCPFCNPJ` e `NomTitularEmpreendimento` não são carregados em memória nem gravados em nenhum artefato (parâmetro `usecols`).

**Modelos de linguagem.** Leem no máximo 512 tokens (~350 palavras): notícias longas são resumidas e classificadas pelo início, e a API informa `truncado: true`. O tom das notícias ficou abaixo da linha de base no benchmark e não é usado como indicador. Detalhes em `docs/escolha_modelo.md`.

**Ano corrente parcial.** A base ANEEL é a de referência 10/2026 (arquivo gerado em 10/10/2026). Os dados de 2026 cobrem até outubro e ficam fora do cálculo de crescimento.

**Potência de 75 kW no Paraná (tratamento aplicado).** A base oficial traz 47 mil registros da COPEL-DIS com potência de exatamente 75 kW, padrão ausente nas demais distribuidoras. A visão corrigida (padrão) imputa a potência mediana de sistemas semelhantes; a potência oficial é preservada, e o seletor "Critério ANEEL" a reproduz. A imputação pode subestimar um pouco os comércios e propriedades rurais que de fato têm 75 kW; o limite conservador, que corrige só as residências, está na Gold (`potencia_mw_conservadora`) e no seletor de visão do painel. Ver [`docs/potencial/atualizacao_base_10_2026.md`](docs/potencial/atualizacao_base_10_2026.md).

---

## 🛣️ Roadmap

- [x] **TP1** — Proposta, organização do projeto, coleta via API e demo Streamlit
- [x] **TP2** — Camadas Silver/Gold, web scraping (BeautifulSoup), interface com cache, estado de sessão e upload
- [x] **TP3** — App multipáginas, API própria (FastAPI), novas fontes (Agência Gov, CONFAZ), KPI de crescimento, testes
- [x] **TP4** — Modelos de linguagem locais (HuggingFace/Transformers): benchmark, resumo e relevância do corpus, `POST /processar_texto` com erros 503/504, Laboratório de IA
- [x] **TP4.5** — Potencial solar municipal: potencial x produção, fatores (SHAP), cenários de irradiação 2030–2050 (NEX-GDDP-CMIP6), página Potencial Solar e rotas `/potencial`
- [ ] **TP5** — Agente inteligente de recomendação usando a API como ferramenta e dashboard final

---

## 📜 Licença dos dados

Este projeto utiliza a base **Relação de Empreendimentos de Geração Distribuída**, publicada pela Agência Nacional de Energia Elétrica (ANEEL):

> This *Relação de Empreendimentos de Geração Distribuída* is made available under the Open Database License: http://opendatacommons.org/licenses/odbl/1.0/. Any rights in individual contents of the database are licensed under the Database Contents License: http://opendatacommons.org/licenses/dbcl/1.0/

A licença ODbL exige atribuição da fonte e possui cláusula *share-alike*: bases derivadas distribuídas publicamente — incluindo os arquivos das camadas Silver e Gold deste repositório — permanecem sob os mesmos termos.

Dados demográficos: **Censo Demográfico 2022** (IBGE), uso livre mediante citação. Notícias: **Agência Brasil** e **Agência Gov** (EBC), reprodução autorizada mediante indicação da fonte, sem finalidade comercial.

---

## 👩‍💻 Autoria

**Pâmela Lima Ziliotto**

Projeto de Bloco — Inteligência Artificial Aplicada à Ciência de Dados

Tema: Desenvolvimento de Soluções Sustentáveis com ESG e a Agenda 2030
