"""
PROJETO: SolarGap Brasil
ARQUIVO: coletor_cmip6.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Coleta o recorte do Brasil da radiação de onda curta incidente na superfície
    (rsds, W/m²) do NEX-GDDP-CMIP6 v2.0 (NASA), para a projeção da irradiação
    municipal em 2030–2050 (TP4.5, Tarefa 6).

FONTE:
    NEX-GDDP-CMIP6 v2.0: projeções diárias com correção de viés e
    desagregação espacial (BCSD), grade global de 0,25°, um NetCDF por modelo,
    cenário, variável e ano. Thrasher et al. (2022), Sci Data 9, 262,
    https://doi.org/10.1038/s41597-022-01393-4. Inventário oficial:
    s3://nex-gddp-cmip6/index_v2.0_md5.txt. Na v2.0, o rsds só difere da v1.0
    em células isoladas do hemisfério norte (Tech Note v2, seção 4.3.5).

MODELOS (todos com rsds em historical, ssp245 e ssp585, variante r1i1p1f1,
"verdes" na tabela do Apêndice I da Tech Note v2):
    ACCESS-CM2 (CSIRO-ARCCSS, Austrália), EC-Earth3 (consórcio europeu),
    GFDL-ESM4 (NOAA-GFDL, EUA), MPI-ESM1-2-HR (MPI-M, Alemanha) e
    MRI-ESM2-0 (MRI, Japão). Critérios em docs/potencial/README.md.

ACESSO (medido em 22/11/2026, MRI-ESM2-0, ssp245, 2030):
    - Arquivo global inteiro no S3: ~274 MB por ano. O chunk interno é um dia
      do globo inteiro (1 x 600 x 1440, gzip), então a leitura preguiçosa de
      um recorte lê o arquivo todo: ~85 GB para 5 modelos x 62 anos.
    - Serviço de recorte THREDDS (NCSS) da NCCS, saída netcdf4: o recorte é
      feito no servidor e chega com 161 x 161 células, ~18,8 MB por ano, em
      ~300 s (o servidor lê o arquivo global). Total ~5,8 GB. É o caminho
      usado aqui. A saída netcdf3 veio truncada no teste e não é usada.

CACHE (camada Bronze, data/raw/cmip6/, ignorada no Git):
    data/raw/cmip6/<modelo>/<cenario>/rsds_<modelo>_<cenario>_<ano>.nc
    Cada arquivo é validado (abre, tem rsds com >= 360 dias na grade esperada)
    antes de entrar no cache; a gravação é atômica (.tmp + rename). Arquivos
    válidos não são baixados de novo: o coletor pode ser interrompido e
    retomado.

NAVEGAÇÃO EDUCADA:
    No máximo 3 requisições simultâneas a um servidor público, User-Agent do
    projeto, retry com backoff exponencial para falhas de rede, resposta
    truncada, HTTP 429 e 5xx.

OBS. DE USO:
    python -m src.data_acquisition.coletor_cmip6               # tudo
    python -m src.data_acquisition.coletor_cmip6 --medir       # 1 modelo/ano
    python -m src.data_acquisition.coletor_cmip6 --modelos MRI-ESM2-0
"""

from __future__ import annotations

import argparse
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests

from src.data_acquisition.coletor_base import (
    calcular_espera_backoff,
    configurar_logging,
    obter_project_root,
)

PROJECT_ROOT = obter_project_root(__file__)
PASTA_CACHE = PROJECT_ROOT / "data" / "raw" / "cmip6"
PASTA_LOGS = PROJECT_ROOT / "logs"

URL_NCSS = "https://ds.nccs.nasa.gov/thredds/ncss/grid/AMES/NEX/GDDP-CMIP6"
VARIAVEL = "rsds"
VARIANTE = "r1i1p1f1"
VERSAO = "_v2.0"

# Grade nativa de cada modelo no NEX-GDDP-CMIP6 (parte do nome do arquivo).
MODELOS = {
    "ACCESS-CM2": "gn",
    "EC-Earth3": "gr",
    "GFDL-ESM4": "gr1",
    "MPI-ESM1-2-HR": "gn",
    "MRI-ESM2-0": "gn",
}
PERIODO_HISTORICO = range(1995, 2015)  # 1995–2014
PERIODO_FUTURO = range(2030, 2051)  # 2030–2050
CENARIOS = {
    "historical": PERIODO_HISTORICO,
    "ssp245": PERIODO_FUTURO,
    "ssp585": PERIODO_FUTURO,
}

# Recorte do Brasil (graus; longitude -180..180).
NORTE, SUL, OESTE, LESTE = 6, -34, -74, -34
CELULAS_ESPERADAS = (161, 161)
DIAS_MINIMOS = 360

USER_AGENT = "SolarGapBrasil/1.0 (projeto academico de ciencia de dados; INFNET)"
MAX_SIMULTANEAS = 3
TENTATIVAS = 4
ESPERA_BASE = 30
TIMEOUT = (30, 1200)  # o servidor leva ~300 s para recortar um ano
STATUS_RETENTAVEIS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class Pedido:
    modelo: str
    cenario: str
    ano: int

    @property
    def nome_arquivo_fonte(self) -> str:
        grade = MODELOS[self.modelo]
        return (
            f"{VARIAVEL}_day_{self.modelo}_{self.cenario}_{VARIANTE}_{grade}_"
            f"{self.ano}{VERSAO}.nc"
        )


def pedidos(modelos: list[str] | None = None) -> list[Pedido]:
    modelos = modelos or list(MODELOS)
    return [
        Pedido(modelo, cenario, ano)
        for modelo in modelos
        for cenario, anos in CENARIOS.items()
        for ano in anos
    ]


def url_recorte(pedido: Pedido) -> str:
    caminho = (
        f"{URL_NCSS}/{pedido.modelo}/{pedido.cenario}/{VARIANTE}/{VARIAVEL}/"
        f"{pedido.nome_arquivo_fonte}"
    )
    parametros = (
        f"var={VARIAVEL}&north={NORTE}&south={SUL}&west={OESTE}&east={LESTE}"
        "&horizStride=1&temporal=all&accept=netcdf4"
    )
    return f"{caminho}?{parametros}"


def caminho_cache(pedido: Pedido, pasta: Path | None = None) -> Path:
    pasta = pasta or PASTA_CACHE
    return (
        pasta
        / pedido.modelo
        / pedido.cenario
        / f"{VARIAVEL}_{pedido.modelo}_{pedido.cenario}_{pedido.ano}.nc"
    )


def arquivo_valido(caminho: Path) -> bool:
    """Abre o NetCDF4 e confere variável, grade e número de dias."""
    import h5py

    try:
        with h5py.File(caminho, "r") as arquivo:
            dados = arquivo[VARIAVEL]
            return (
                dados.ndim == 3
                and dados.shape[1:] == CELULAS_ESPERADAS
                and dados.shape[0] >= DIAS_MINIMOS
                and "lat" in arquivo
                and "lon" in arquivo
            )
    except (OSError, KeyError):
        return False


_local = threading.local()


def _sessao() -> requests.Session:
    if not hasattr(_local, "sessao"):
        _local.sessao = requests.Session()
        _local.sessao.headers["User-Agent"] = USER_AGENT
    return _local.sessao


def baixar(pedido: Pedido, pasta: Path | None = None) -> tuple[Path, int, float]:
    """Baixa (com retry) e valida um recorte. Devolve (caminho, bytes, segundos)."""
    destino = caminho_cache(pedido, pasta)
    if destino.exists() and arquivo_valido(destino):
        return destino, 0, 0.0
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".tmp")
    url = url_recorte(pedido)

    for tentativa in range(1, TENTATIVAS + 1):
        inicio = time.time()
        try:
            resposta = _sessao().get(url, timeout=TIMEOUT, stream=True)
            if resposta.status_code in STATUS_RETENTAVEIS:
                raise requests.HTTPError(f"HTTP {resposta.status_code}")
            resposta.raise_for_status()
            with open(temporario, "wb") as saida:
                saida.writelines(resposta.iter_content(2**20))
            if not arquivo_valido(temporario):
                raise ValueError("arquivo incompleto ou inválido")
            temporario.replace(destino)
            return destino, destino.stat().st_size, time.time() - inicio
        except (requests.RequestException, ValueError) as erro:
            temporario.unlink(missing_ok=True)
            if tentativa == TENTATIVAS:
                raise RuntimeError(f"{pedido}: {erro}") from erro
            espera = calcular_espera_backoff(tentativa, ESPERA_BASE)
            logging.warning(
                "%s, tentativa %d/%d falhou (%s); nova tentativa em %ds",
                pedido,
                tentativa,
                TENTATIVAS,
                erro,
                espera,
            )
            time.sleep(espera)
    raise AssertionError("inalcançável")


def coletar(
    lista: list[Pedido], max_simultaneas: int = MAX_SIMULTANEAS
) -> dict[str, float]:
    resumo = {"baixados": 0, "em_cache": 0, "falhas": 0, "bytes": 0, "segundos": 0.0}
    inicio = time.time()
    with ThreadPoolExecutor(max_workers=max_simultaneas) as executor:
        futuros = {executor.submit(baixar, p): p for p in lista}
        for i, futuro in enumerate(as_completed(futuros), start=1):
            pedido = futuros[futuro]
            try:
                _, tamanho, segundos = futuro.result()
            except RuntimeError as erro:
                resumo["falhas"] += 1
                logging.error("Falhou: %s", erro)
                continue
            if tamanho:
                resumo["baixados"] += 1
                resumo["bytes"] += tamanho
                logging.info(
                    "[%d/%d] %s %s %d: %.1f MB em %.0fs",
                    i,
                    len(lista),
                    pedido.modelo,
                    pedido.cenario,
                    pedido.ano,
                    tamanho / 1e6,
                    segundos,
                )
            else:
                resumo["em_cache"] += 1
    resumo["segundos"] = time.time() - inicio
    logging.info(
        "Resumo: %d baixados (%.2f GB), %d em cache, %d falhas, %.1f h",
        resumo["baixados"],
        resumo["bytes"] / 1e9,
        resumo["em_cache"],
        resumo["falhas"],
        resumo["segundos"] / 3600,
    )
    return resumo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recortes do Brasil do rsds (NEX-GDDP-CMIP6)."
    )
    parser.add_argument("--modelos", nargs="+", choices=list(MODELOS))
    parser.add_argument(
        "--medir",
        action="store_true",
        help="Baixa um único modelo/ano e estima o volume total.",
    )
    argumentos = parser.parse_args()
    configurar_logging("CMIP6", PASTA_LOGS)
    lista = pedidos(argumentos.modelos)
    if argumentos.medir:
        resumo = coletar(lista[:1], max_simultaneas=1)
        tamanho = caminho_cache(lista[0]).stat().st_size
        logging.info(
            "Estimativa: %d arquivos x %.1f MB = %.2f GB",
            len(pedidos()),
            tamanho / 1e6,
            len(pedidos()) * tamanho / 1e9,
        )
        return
    resumo = coletar(lista)
    if resumo["falhas"]:
        raise SystemExit(
            f"{resumo['falhas']} arquivo(s) falharam; rode de novo para retomar."
        )


if __name__ == "__main__":
    main()
