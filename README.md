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

### Indicadores

| KPI | Definição |
|---|---|
| Watts por habitante | Potência solar instalada dividida pela população (Censo 2022), por estado |
| Empreendimentos por 100 mil hab. | Difusão: sistemas conectados para cada 100 mil habitantes |
| Ranking de disparidade | Posição das 27 UFs em cada métrica, com a média nacional como referência |
| Taxa de crescimento | Crescimento anual do parque instalado e CAGR por UF desde a Lei 14.300 (2022–2025) |

### Principais achados (TP3)

- O parque solar distribuído passou de 18,3 GW (2022) para 47,5 GW (2025): **37,5% ao ano**. O ritmo desacelera (48% em 2023, 26% em 2025).
- **10 "mercados emergentes"** — adoção abaixo da média nacional, crescimento acima: RR, AL, AC, BA, PA, AM, CE, PE, SP e SE.
- **3 "lacunas persistentes"** — adoção e crescimento abaixo da média: RJ, DF e PB.
- A correção de preenchimento do Maranhão muda a leitura de política pública: com ela, o MA é "líder em expansão"; no critério do painel oficial da ANEEL, cairia em "lacuna persistente".
- O momento de adesão à isenção de ICMS (Convênio 16/15) não se relaciona com a adoção atual (Spearman −0,06).

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
│   └── external/                 # referências de terceiros curadas (texto do Convênio ICMS 16/15)
├── docs/
│   ├── project_charter_solargap.docx
│   ├── data_summary_report.md
│   └── api.md
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
│   ├── servicos/                 # regra de negócio usada pelo app E pela API (TP3)
│   ├── api/                      # API FastAPI (TP3)
│   │   ├── main.py               #   aplicação e tratamento de erros
│   │   ├── modelos.py            #   modelos Pydantic de entrada e resposta
│   │   └── rotas/                #   sistema, indicadores, notícias, políticas, comparações
│   └── app/                      # dashboard Streamlit multipáginas (TP3)
│       ├── app.py                #   entrada: menu de navegação e filtros globais
│       └── paginas/              #   Início, Panorama, Evolução, Oportunidades, Notícias, Dados, API
├── tests/                        # 67 testes automatizados (pytest)
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
pip install -r requirements.txt
```

**Dashboard** (a partir da raiz):

```bash
python -m streamlit run src/app/app.py
```

**API** (em outro terminal, a partir da raiz):

```bash
uvicorn src.api.main:app --reload
# Documentação interativa: http://127.0.0.1:8000/docs
```

O dashboard funciona sem a API; a página **API** do dashboard mostra o status, consulta as rotas e envia notícias quando a API está no ar.

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

**Ano corrente parcial.** Os dados de 2026 cobrem até agosto e ficam fora do cálculo de crescimento.

---

## 🛣️ Roadmap

- [x] **TP1** — Proposta, organização do projeto, coleta via API e demo Streamlit
- [x] **TP2** — Camadas Silver/Gold, web scraping (BeautifulSoup), interface com cache, estado de sessão e upload
- [x] **TP3** — App multipáginas, API própria (FastAPI), novas fontes (Agência Gov, CONFAZ), KPI de crescimento, testes
- [ ] **TP4** — Modelo de linguagem local (HuggingFace/Transformers): resumo e sentimento do corpus via `POST /processar_texto`
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
