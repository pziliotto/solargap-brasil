"""
Configuração comum dos testes (pytest).

Rodar a partir da raiz do projeto:
    python -m pytest            # todos
    python -m pytest -k api     # só os da API

Os testes usam a camada Gold versionada (data/processed) como dado real de
leitura. Tudo o que GRAVA (notícias enviadas, Gold sintética) vai para pastas
temporárias (tmp_path), sem tocar nos arquivos do projeto.
"""

import shutil
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

PASTA_PROCESSED = RAIZ / "data" / "processed"
PASTA_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def pasta_processed_temporaria(tmp_path: Path) -> Path:
    """Cópia da Gold real numa pasta temporária (para testes que gravam)."""
    destino = tmp_path / "processed"
    shutil.copytree(PASTA_PROCESSED, destino)
    return destino


@pytest.fixture
def fixture():
    """Lê um arquivo de tests/fixtures pelo nome."""
    return lambda nome: (PASTA_FIXTURES / nome).read_text(encoding="utf-8")
