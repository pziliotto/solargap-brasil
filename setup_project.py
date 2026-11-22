"""
Script de Configuração Automática do Projeto
Energia Solar Brasil

Autora: Pâmela Lima Ziliotto
Data: 17/08/2026
Atualizado: 13/11/2026 — TP4: pastas src/ia e docs/benchmark
            21/10/2026 — TP3: pastas da API, serviços, páginas, testes e data/external;
            .gitignore e requirements sincronizados com os arquivos da raiz
OBS: Com o andamento do projeto serão criadas outras funções, "env", "sample_config" e "requirements". Assim como qualquer outra função que o projeto precise para que ao final, esse arquivo permita o setup completo em qualquer máquina.
"""

import os  # noqa: F401
from pathlib import Path


def create_directory_structure():
    """Cria toda a estrutura de diretórios do projeto"""

    directories = [
        # Dados
        "data/raw",  # CSVs originais da ANEEL/IBGE
        "data/interim",  # Etapa Silver, dados em processamento
        "data/processed",  # Dados Gold, prontos para o APP
        "data/external",  # Referências de terceiros curadas (TP3)
        # Documentos
        "docs",
        # Código Fonte
        "src/data_acquisition/",  # scripts de API/scrapping
        "src/data_acquisition/noticias",  # scrapers de notícias (TP3)
        "src/preparacao",  # camadas Silver e Gold
        "src/servicos",  # regra de negócio compartilhada (TP3)
        "src/api/rotas",  # API FastAPI (TP3)
        "src/app/paginas",  # páginas do app multipáginas (TP3)
        "src/ia",  # modelos de linguagem locais (TP4)
        "docs/benchmark",  # rótulos e resultados do benchmark de modelos (TP4)
        "tests/fixtures",  # testes automatizados (TP3)
        # Notebooks
        "notebooks",  # exploração inicial
        # Outputs
        "outputs/quality_reports",
        # Logs de trabalho
        "logs",
    ]

    print("🚀 Criando estrutura de diretórios...\n")

    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✅ Criado: {directory}/")

    print("\n" + "=" * 60)


def create_gitignore():
    """Cria arquivo .gitignore"""

    gitignore_content = """# ═══════════════════ Python ═══════════════════
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/
.venv

# ═══════════════════ Jupyter Notebooks ═══════════════════

.ipynb_checkpoints
*.ipynb_checkpoints/

# ═══════════════════ IDEs ═══════════════════
.vscode/
.idea/
*.swp
*.swo

# ═══════════════════ Dados ═══════════════════
# Camada Bronze (raw)
# Ignora tudo por padrão; libera apenas o que é pequeno.
# HTML de noticias fica em data/raw/html/ -> cache descartável
data/raw/*
!data/raw/.gitkeep

# IBGE — arquivos pequenos (UF ~0.01 MB, municípios ~1.9 MB)
!data/raw/demografico_uf_2022.json
!data/raw/demografico_municipio_2022.json

# IBGE — domicílios particulares permanentes ocupados por município (TP4.5,
# SIDRA 4712, ~1.9 MB). Fica em subpasta: libera a pasta, ignora o conteúdo
# e reinclui só o JSON de domicílios.
!data/raw/ibge/
data/raw/ibge/*
!data/raw/ibge/domicilios_municipio_2022.json

# IBGE — fatores municipais do Censo 2022 (TP4.5, Tarefa 3), SIDRA view=flat:
# 4714 (população, área, densidade, ~3.2 MB), 9923 (população por situação do
# domicílio, ~3.3 MB) e 10295 (rendimento domiciliar per capita, ~5.5 MB).
# A base do PIB dos Municípios (pib_municipios/, ~21 MB) segue ignorada.
!data/raw/ibge/populacao_area_densidade_municipio_2022.json
!data/raw/ibge/populacao_situacao_municipio_2022.json
!data/raw/ibge/renda_domiciliar_pc_municipio_2022.json

# ANEEL — base completa tem ~103 MB e estoura o limite de 100 MB do
# GitHub. Só a amostra usada pelo app demo é versionada.
# Para obter a base completa: python -m src.data_acquisition.aneel
!data/raw/amostra_*.parquet
!data/raw/amostra_*.csv

# NASA POWER (TP4.5) — cache de um JSON por célula de 1° (~600 arquivos).
# Reproduzível e retomável: python -m src.data_acquisition.coletor_nasa_power
# Já coberto por data/raw/*; a regra explícita impede que uma futura exceção
# com "!" volte a versionar o cache por engano.
data/raw/nasa_power/

# NEX-GDDP-CMIP6 (TP4.5, Tarefa 6) — recortes do Brasil da variável rsds, um
# NetCDF por modelo/cenário/ano (~19 MB cada, ~5,8 GB no total). Reproduzível:
# python -m src.data_acquisition.coletor_cmip6
data/raw/cmip6/

# ── Camada Silver (interim) ──
# Sempre reproduzível a partir do raw + scripts de tratamento.
data/interim/*
!data/interim/.gitkeep

# ── Camada Gold (processed) ──
# VERSIONADA — é o que alimenta o dashboard. Nada a ignorar aqui.

# ── Dados externos (external) ──
# VERSIONADA: referências de terceiros curadas manualmente, com fonte
# documentada (ex.: texto oficial do Convênio ICMS 16/15).
# Exceção: notícias recebidas pela API são estado de execução, não dado do projeto.
data/external/noticias_enviadas.csv

# ═══════════════════ Modelos treinados ═══════════════════
# Reproduzíveis a partir das Gold com semente fixa: python -m src.potencial.modelo
models/

# ═══════════════════ Testes e lint ═══════════════════
.pytest_cache/
.ruff_cache/

# ═══════════════════ LOGS ═══════════════════
logs/
*.log

# ═══════════════════ OS ═══════════════════
.DS_Store
Thumbs.db

# Travas de edição do LibreOffice (arquivo aberto no editor)
.~lock.*#

# ═══════════════════ Outputs Gerados ═══════════════════
outputs/quality_reports/

# ═══════════════════ Environment variables ═══════════════════
.env
.env.local
"""
    with open(".gitignore", "w", encoding="utf-8") as f:
        f.write(gitignore_content)

    print("✅ Criado: .gitignore")


def create_requirements():
    """Cria arquivo requirements.txt com dependências do projeto"""

    requirements_content = """# Streamlit
altair==6.2.2
blinker==1.9.0
narwhals==2.24.0
pydeck==0.9.3
streamlit==1.61.1
tenacity==9.1.4
watchdog==6.0.0

# Data Science / Análise de Dados
numpy==2.5.2
pandas==3.0.5
pyarrow==24.0.0

# Visualização
matplotlib-inline==0.2.2
plotly==7.1.0
wordcloud==1.9.6

# Jupyter / JupyterLab
ipykernel==7.3.0
ipython==9.16.1
ipython_pygments_lexers==1.1.1
jupyter_client==8.9.1
jupyter_core==5.9.1
jupyter_events==0.12.1
jupyter-lsp==2.3.1
jupyter_builder==1.2.2
jupyter_server==2.20.0
jupyter_server_terminals==0.5.4
jupyterlab==4.6.3
jupyterlab_pygments==0.3.0
jupyterlab_server==2.28.0
nbclient==0.11.0
nbconvert==7.17.1
nbformat==5.11.1
notebook==7.6.2
notebook_shim==0.2.4
qtconsole==5.7.0

# Web / HTTP
anyio==4.14.2
certifi==2026.7.22
charset-normalizer==3.5.1
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
httptools==0.8.0
idna==3.18
requests==2.34.2
urllib3==2.7.0
websocket-client==1.9.0
websockets==16.1.1

# Web Scraping / HTML / XML
beautifulsoup4==4.15.0
soupsieve==2.9.2
bleach==6.4.0
defusedxml==0.7.1
lxml==6.0.0
# robots.txt conforme a RFC 9309 (curingas * e $), usado pelo Navegador
protego==0.7.0

# ASGI / Servidor Web
starlette==1.3.1
uvicorn==0.52.3
python-multipart==0.0.32

# Templates / Web Utilities
Jinja2==3.1.6
MarkupSafe==3.0.3
itsdangerous==2.2.0

# JSON / YAML / Schemas
json5==0.15.0
jsonpointer==3.1.1
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
PyYAML==6.0.3
referencing==0.37.0
rpds-py==2026.6.3

# Data / Formatos / Datas
arrow==1.4.0
babel==2.18.0
fqdn==1.5.0
isoduration==20.11.0
rfc3339-validator==0.1.4
rfc3986-validator==0.1.1
rfc3987-syntax==1.1.0
uri-template==1.3.0
tzdata==2026.3
python-dateutil==2.9.0.post0

# Sistema / Ambiente Python
packaging==26.3
platformdirs==4.11.3
psutil==7.2.2
pywinpty==3.0.0
setuptools==80.9.0
six==1.17.0
typing_extensions==4.16.0

# Terminal / Desenvolvimento
asttokens==3.0.2
colorama==0.4.6
comm==0.2.3
debugpy==1.8.21
executing==2.2.1
jedi==0.20.0
parso==0.8.7
prompt_toolkit==3.0.53
Pygments==2.21.0
pure_eval==0.2.3
stack-data==0.6.3
traitlets==5.16.1
wcwidth==0.8.2

# Segurança / Criptografia
argon2-cffi==25.1.0
argon2-cffi-bindings==25.1.0
cffi==2.1.1
pycparser==3.0

# XML / Sanitização / Markdown
mistune==3.3.4
pandocfilters==1.5.1
tinycss2==1.5.0
webcolors==25.10.0
webencodings==0.6.1

# Comunicação / Async
async-lru==2.3.0
nest-asyncio2==1.7.2
tornado==6.5.8

# Processamento / Validação
attrs==26.1.0
fastjsonschema==2.22.2
lark==1.3.1

# Arquivos / Imagens
pillow==12.3.0
Send2Trash==2.1.0

# Sistema de Execução / Monitoramento
prometheus_client==0.26.0
terminado==0.18.1

# Protocolos / Serialização
protobuf==7.36.2

# API (TP3)
fastapi==0.159.1
pydantic==2.14.1
pydantic_core==2.50.1
annotated-types==0.8.0
annotated-doc==0.0.5
typing-inspection==0.4.4
opentelemetry-api==1.45.1

# Testes e qualidade de código (TP3)
pytest==9.1.1
iniconfig==2.3.1
pluggy==1.7.0
ruff==0.17.1

# Geoespacial (TP4.5) — malha municipal do IBGE via geobr
# duckdb fica em 1.x: o geobr 2.1.1 usa Relation.fetchone(), removido no duckdb 2.0
geobr==2.1.1
geopandas==1.2.0
shapely==2.2.0
pyogrio==0.13.0
pyproj==3.8.0
duckdb==1.5.6

# Leitura de planilhas .xlsx (TP4.5: PIB dos Municípios e MapBiomas)
openpyxl==3.1.5
et-xmlfile==2.0.0

# Leitura dos recortes NetCDF4/HDF5 do NEX-GDDP-CMIP6 (TP4.5, Tarefa 6)
h5py==3.16.0

# Modelo explicativo e SHAP (TP4.5, Tarefa 4)
scikit-learn==1.9.1
lightgbm==4.7.0
shap==0.54.1
scipy==1.18.1
joblib==1.6.0
threadpoolctl==3.8.0
cloudpickle==3.1.3
slicer==0.0.8

# IA local (TP4) — modelos de linguagem com Transformers/PyTorch
# ATENÇÃO (Windows + GPU NVIDIA): instale o torch ANTES deste arquivo, pelo
# índice do PyTorch, senão o pip baixa a versão só-CPU do PyPI:
#   pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cu132
# Sem GPU, o pip install -r requirements.txt instala a versão CPU normalmente.
torch==2.15.0
transformers==5.23.0
tokenizers==0.23.3
sentencepiece==0.2.3
safetensors==0.8.0
huggingface_hub==2.4.0
hf-xet==1.8.0
regex==2026.11.9
tqdm==4.70.1
filelock==4.2.10
fsspec==2026.9.0
sympy==1.14.0
mpmath==1.3.0
networkx==3.7
"""

    with open("requirements.txt", "w", encoding="utf-8") as f:
        f.write(requirements_content)

    print("✅ Criado: requirements.txt")


def create_init_files():
    """Cria arquivos __init__.py para tornar diretórios em pacotes Python."""

    init_dirs = [
        "src",
        "src/data_acquisition",
        "src/data_acquisition/noticias",
        "src/preparacao",
        "src/servicos",
        "src/ia",
        "src/api",
        "src/api/rotas",
        "src/app",
        "tests",
    ]

    for directory in init_dirs:
        init_file = Path(directory) / "__init__.py"
        init_file.touch()

    print("✅ Criados: arquivos __init__.py")


def main():
    """Função principal"""

    print("\n" + "=" * 60)
    print("⚡Setup - Análise de Energia Solar Brasil")
    print("=" * 60 + "\n")

    funcoes = [
        ("Estrutura de diretórios", create_directory_structure),
        (".gitignore", create_gitignore),
        ("Arquivos __init__.py", create_init_files),
        ("requirements.txt", create_requirements),
    ]

    for nome, funcao in funcoes:
        try:
            funcao()
        except FileExistsError:
            print(f"⚠️   {nome} já existe, pulando...")
        except Exception as e:
            print(f"❌  Erro ao criar {nome}: {e}")

    print("\n" + "=" * 60)
    print("✨ SETUP CONCLUÍDO!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
