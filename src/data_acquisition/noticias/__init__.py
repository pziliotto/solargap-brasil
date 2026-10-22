"""
PROJETO: SolarGap Brasil
PACOTE: src.data_acquisition.noticias
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 20/09/2026 (módulo único noticias.py, TP2)
ATUALIZAÇÃO: 21/10/2026 — TP3: virou pacote com várias fontes

DESCRIÇÃO:
    Coleta de notícias sobre energia solar e geração distribuída por web
    scraping estático (BeautifulSoup), para o corpus do projeto.

EVOLUÇÃO TP2 -> TP3:
    TP2: uma fonte (Agência Brasil), lógica toda em noticias.py.
    TP3: fontes declaradas em fontes.py e coleta genérica em coletor.py. Uma
         fonte nova é uma entrada de configuração, não um script novo.

MÓDULOS:
    base.py     navegação educada (robots.txt por domínio, pausa, retry) e
                extração independente de layout (meta tags, JSON-LD, <p>)
    fontes.py   fontes avaliadas: habilitadas, desabilitadas e não incluídas,
                com licença e justificativa
    coletor.py  orquestração, mescla incremental com o corpus e resumo

USO (a partir da raiz):
    python -m src.data_acquisition.noticias                 # fontes habilitadas
    python -m src.data_acquisition.noticias --listar        # situação das fontes
    python -m src.data_acquisition.noticias --fontes agenciagov
    python -m src.data_acquisition.noticias --reprocessar   # reextrai do cache
"""

from src.data_acquisition.noticias.coletor import coletar_noticias

__all__ = ["coletar_noticias"]
