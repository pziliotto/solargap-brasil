"""
PROJETO: SolarGap Brasil
PACOTE: src.servicos
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026

DESCRIÇÃO:
    Camada de serviços: toda a regra de negócio que transforma a camada Gold em
    indicadores, séries, rankings e recortes de notícias.

POR QUE EXISTE (TP3):
    No TP2 esses cálculos moravam em src/app/carregamento.py, presos ao
    Streamlit (@st.cache_data). Com a API, o mesmo cálculo passou a ter dois
    consumidores. Manter duas cópias faria o painel e a API divergirem com o
    tempo — o mesmo indicador com dois valores.

    A regra agora vive aqui, em pandas puro, sem importar Streamlit nem FastAPI:
        dashboard (src/app)  ─┐
                              ├──> src/servicos ──> data/processed (Gold)
        API (src/api)       ──┘

    No TP5, o agente inteligente consumirá esta mesma camada (via API), o que
    garante que as recomendações usem exatamente os números exibidos no painel.

MÓDULOS:
    dados.py        leitura dos arquivos da Gold e das contribuições externas
    indicadores.py  indicadores per capita, séries, crescimento e oportunidades
    noticias.py     corpus de notícias: filtros, registro de novas notícias
    texto.py        tokenização, frequência de termos e preparo de texto para LLM
"""
