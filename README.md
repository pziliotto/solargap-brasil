# ☀️ SolarGap Brasil

### Onde está o próximo mercado solar?

Mapeamento da desigualdade regional na adoção de energia solar distribuída no Brasil, a partir de dados abertos da ANEEL e do IBGE.

O projeto quantifica a disparidade entre unidades da federação na adoção de micro e minigeração distribuída (MMGD), normalizada pela população — revelando tanto os estados que ficam para trás na transição energética quanto os mercados ainda inexplorados pelo setor solar.

**Objetivos de Desenvolvimento Sustentável:** ODS 7 (Energia Limpa e Acessível) · ODS 10 (Redução das Desigualdades)

---

## 📋 Sobre o projeto

Desde a Lei nº 14.300/2022 — o Marco Legal da Geração Distribuída — a energia solar distribuída se expandiu de forma acelerada no Brasil, mas não de maneira homogênea entre os estados. Este projeto mapeia e quantifica essas assimetrias por meio de um painel interativo.

Documentação completa:

- 📄 [Project Charter](docs/project_charter.docx) — escopo, objetivos, KPIs, stakeholders e cronograma
- 📊 [Data Summary Report](docs/data_summary_report.md) — fontes, qualidade, tratamento e licenciamento dos dados

### Indicadores

| KPI | Definição |
|---|---|
| Potência instalada per capita | MW de MMGD instalados por 100 mil habitantes, por estado |
| Taxa de crescimento anual | Variação percentual ano a ano da potência instalada, por estado |
| Ranking de disparidade | Os 5 estados com maior e os 5 com menor adoção per capita |

---

## 🗂️ Fontes de dados

| Fonte | Conteúdo | Acesso |
|---|---|---|
| ANEEL — Relação de Empreendimentos de Geração Distribuída | ~4,7 milhões de registros de empreendimentos MMGD | Portal de Dados Abertos (CKAN) |
| IBGE — Censo Demográfico 2022 | População residente por UF e por município | API de Agregados v3, tabela 9923 |

Detalhamento em [`docs/data_summary_report.md`](docs/data_summary_report.md).

---

## 📁 Estrutura do projeto

```
solargap-brasil/
├── data/
│   ├── raw/                      # 🥉 Bronze — dados originais, sem transformação
│   ├── interim/                  # 🥈 Silver — limpos e tipados (não versionado)
│   └── processed/                # 🥇 Gold — agregados, prontos para a aplicação
├── docs/
│   ├── project_charter.docx
│   └── data_summary_report.md
├── logs/                         # logs de execução por coleta (não versionado)
├── notebooks/                    # exploração e análise
├── outputs/
│   └── quality_reports/          # relatórios de diagnóstico de qualidade
├── src/
│   ├── data_acquisition/
│   │   ├── coletor_base.py       # infraestrutura compartilhada (retry, logging, paths)
│   │   ├── aneel.py              # download em streaming da base MMGD
│   │   └── ibge.py               # coleta populacional (UF e município)
│   ├── preparacao/
│   │   ├── gerar_amostra.py      # amostra estratificada por UF para o repositório
│   │   └── diagnostico_temporal.py  # validação dos campos de data
│   └── app/                      # aplicação Streamlit
│      └── demo_app.py            # visualização inicial dos dados no streamlit
├── .gitignore
├── requirements.txt
├── setup_project.py              # cria a estrutura de diretórios do zero
└── README.md
```

### Arquitetura de dados

O projeto segue a arquitetura *medallion* (Bronze / Silver / Gold):

| Camada | Diretório | Conteúdo | Versionado |
|---|---|---|---|
| 🥉 Bronze | `data/raw/` | Cópia fiel da fonte, nunca editada | Parcial¹ |
| 🥈 Silver | `data/interim/` | Limpo, tipado, ainda granular | ❌ Reproduzível |
| 🥇 Gold | `data/processed/` | Agregado e normalizado, consumido pelo app | ✅ Sim |

¹ Os arquivos do IBGE (~1,9 MB) e a amostra estratificada da ANEEL são versionados. A base completa da ANEEL **não é** — ver seção abaixo.

---

## 🚀 Como rodar

**Pré-requisitos:** Python 3.11 ou superior.

```bash
# 1. Clonar o repositório
git clone https://github.com/<pziliotto>/solargap-brasil.git
cd solargap-brasil

# 2. Criar e ativar o ambiente virtual
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate
# Linux / macOS
source .venv/bin/activate

# 3. Instalar as dependências
pip install -r requirements.txt

# 4. Executar a aplicação (na raiz)
python -m streamlit run src/app/demo_app.py
```

A aplicação funciona imediatamente após o clone, usando a amostra versionada — **não é necessário baixar a base completa** para avaliar o projeto.

### Coleta de dados (opcional)

Para regenerar as bases a partir das fontes originais:

```bash
python -m src.data_acquisition.ibge      # população por UF e município
python -m src.data_acquisition.aneel     # base MMGD completa (~105 MB)
python -m src.preparacao.gerar_amostra   # amostra estratificada para o repositório
```

> ⚠️ **Os scripts devem ser executados a partir da raiz do projeto**, com a sintaxe `python -m pacote.modulo` (pontos, sem `.py`). Executá-los diretamente (`python src/data_acquisition/ibge.py`) provoca `ModuleNotFoundError`, porque o Python não enxergaria `src` como pacote.

---

## ⚠️ Limitações conhecidas

**Restrição geográfica da ANEEL.** O Portal de Dados Abertos da ANEEL aplica filtragem por IP de origem. A execução de `aneel.py` a partir de fora do território brasileiro falha; é necessária VPN com saída no Brasil. Essa restrição **não afeta a avaliação do projeto**, já que a amostra e a camada Gold estão versionadas.

**Base completa fora do versionamento.** O arquivo da ANEEL tem ~105 MB compactado (~1,4 GB descompactado), acima do limite de 100 MB por arquivo do GitHub. O repositório contém uma **amostra estratificada por UF** (até 40 registros de cada estado), suficiente para executar o app demo. A base completa é obtida com o comando de coleta acima.

**Dados pessoais excluídos na origem.** As colunas `NumCPFCNPJ` e `NomTitularEmpreendimento` da base original não são carregadas em memória nem gravadas em disco em nenhum artefato do projeto (parâmetro `usecols` na leitura), em conformidade com o princípio de minimização de dados.

**Ano corrente parcial.** Os dados de 2026 cobrem apenas parte do ano (referência 08/2026) e não devem ser comparados diretamente com anos completos.

---

## 🛣️ Roadmap

- [x] **TP1** — Proposta, organização do projeto, coleta via API e demo Streamlit
- [ ] **TP2** — Interface interativa, web scraping (BeautifulSoup), cache e upload de arquivos
- [ ] **TP3** — Múltiplas páginas, scraping dinâmico (Selenium) e API própria (FastAPI)
- [ ] **TP4** — Integração de modelo de linguagem local (HuggingFace/Transformers)
- [ ] **TP5** — Agente inteligente de recomendação e dashboard final

---

## 📜 Licença dos dados

Este projeto utiliza a base **Relação de Empreendimentos de Geração Distribuída**, publicada pela Agência Nacional de Energia Elétrica (ANEEL):

> This *Relação de Empreendimentos de Geração Distribuída* is made available under the Open Database License: http://opendatacommons.org/licenses/odbl/1.0/. Any rights in individual contents of the database are licensed under the Database Contents License: http://opendatacommons.org/licenses/dbcl/1.0/

A licença ODbL exige atribuição da fonte e possui cláusula *share-alike*: bases derivadas distribuídas publicamente — incluindo os arquivos das camadas Silver e Gold deste repositório — permanecem sob os mesmos termos.

Os dados demográficos são provenientes do **Censo Demográfico 2022** do Instituto Brasileiro de Geografia e Estatística (IBGE), de uso livre mediante citação da fonte.

---

## 👩‍💻 Autoria

**Pâmela Lima Ziliotto**
Projeto de Bloco — Inteligência Artificial Aplicada à Ciência de Dados
Tema: Desenvolvimento de Soluções Sustentáveis com ESG e a Agenda 2030
