"""
PROJETO: SolarGap Brasil
ARQUIVO: app.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026 (substitui demo_app.py, de 20/08/2026)
ATUALIZAÇÃO:

DESCRIÇÃO:
    Arquivo de entrada do dashboard multipáginas (TP3). Configura a página,
    monta o menu de navegação, desenha os filtros globais e executa a página
    escolhida pelo usuário.

EVOLUÇÃO:
    TP1 — demo_app.py: página única com tabelas de amostra
    TP2 — demo_app.py: quatro abas (st.tabs), cache e estado de sessão
    TP3 — app.py + paginas/: cada análise vira uma página (st.navigation),
          com menu agrupado por seção e duas páginas novas (Oportunidades e API)

POR QUE st.navigation E NÃO A PASTA pages/:
    A pasta pages/ monta o menu a partir dos nomes dos arquivos. Com
    st.navigation o menu é declarado no código: títulos, ícones, agrupamento
    em seções e — o ponto decisivo — um arquivo de entrada que roda antes de
    toda página. É nele que ficam os filtros globais, sem repetição.

ESTRUTURA DO MENU:
    Visão geral  — Início
    Análises     — Panorama · Evolução e crescimento · Oportunidades
    Contexto     — Notícias
    Ferramentas  — Dados · API

OBS. DE USO:
    Rodar a partir da raiz:
        python -m streamlit run src/app/app.py
    Para a página API, a API precisa estar rodando em outro terminal:
        uvicorn src.api.main:app --reload
"""

import sys
from pathlib import Path

# Garante que a raiz do projeto esteja no path (este arquivo está em src/app/)
RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import streamlit as st  # noqa: E402

from src.app import carregamento as dados  # noqa: E402
from src.app import componentes  # noqa: E402
from src.servicos.dados import DadosIndisponiveis  # noqa: E402

st.set_page_config(page_title="SolarGap - Brasil", page_icon="☀️", layout="wide")

# Caminhos relativos ao arquivo de entrada: é assim que o st.Page os resolve.
PAGINAS = {
    "Visão geral": [
        st.Page("paginas/inicio.py", title="Início", icon="☀️", default=True),
    ],
    "Análises": [
        st.Page("paginas/panorama.py", title="Panorama", icon="📊"),
        st.Page("paginas/evolucao.py", title="Evolução e crescimento", icon="📈"),
        st.Page("paginas/oportunidades.py", title="Oportunidades", icon="🎯"),
    ],
    "Contexto": [
        st.Page("paginas/noticias.py", title="Notícias", icon="📰"),
    ],
    "Ferramentas": [
        st.Page("paginas/dados.py", title="Dados", icon="📁"),
        st.Page("paginas/api.py", title="API", icon="🔌"),
    ],
}

# Páginas que usam os filtros de indicadores. Nas demais, a barra lateral
# mostra só as inspirações, e os valores escolhidos ficam guardados na sessão.
PAGINAS_COM_FILTROS = {"Panorama", "Evolução e crescimento", "Oportunidades", "Dados"}

pagina = st.navigation(PAGINAS)

try:
    agregado = dados.carregar_agregado()
except DadosIndisponiveis as erro:
    st.error(f"Não foi possível carregar a camada Gold: {erro}")
    st.stop()

if pagina.title in PAGINAS_COM_FILTROS:
    st.session_state["filtros"] = componentes.barra_lateral_filtros(agregado)

with st.sidebar:
    st.divider()
    st.markdown(
        """
**Inspirações do projeto**
- [ODS 7 — Energia limpa e acessível (ONU Brasil)](https://brasil.un.org/pt-br/sdgs/7)
- [Desertec — o debate sobre energia solar no Saara](https://www.desertec.org)
- [EPE — estudos de micro e minigeração distribuída](https://www.epe.gov.br)

**Contexto regulatório**
- [Lei 14.300/2022](https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2022/lei/l14300.htm)
"""
    )

pagina.run()
