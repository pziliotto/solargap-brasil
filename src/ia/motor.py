"""
PROJETO: SolarGap Brasil
ARQUIVO: motor.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 13/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Gerenciador dos modelos de linguagem: carrega cada modelo UMA vez, guarda o
    estado de cada tarefa e executa as inferências em fila.

CICLO DE VIDA DE CADA TAREFA:
    nao_carregado -> carregando -> pronto
                                -> falhou   (erro guardado e exposto na API)

    A API inicia a carga em segundo plano: ela sobe na hora, e enquanto os
    modelos carregam as rotas de IA respondem 503 com Retry-After. Se a carga
    falhar (sem internet no primeiro download, PyTorch ausente, falta de
    memória), o resto da API continua funcionando.

MODELO COMPARTILHADO:
    tom e relevância usam o mesmo classificador NLI. Ele é carregado uma única
    vez e as duas tarefas apontam para a mesma instância.

FILA DE INFERÊNCIA:
    Um lock garante uma inferência por vez. Duas requisições simultâneas na GPU
    de 6 GB disputariam memória; em fila, a segunda só espera.

TESTABILIDADE:
    A fábrica de modelos é injetável. Os testes passam uma fábrica falsa e
    exercitam todos os estados e erros sem PyTorch e sem download.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.ia import catalogo
from src.ia.catalogo import ModeloConfig, Tarefa

logger = logging.getLogger(__name__)

SEGUNDOS_RETRY_CARREGANDO = 30


class EstadoModelo(str, Enum):
    nao_carregado = "nao_carregado"
    carregando = "carregando"
    pronto = "pronto"
    falhou = "falhou"


class ModeloIndisponivel(RuntimeError):
    """A tarefa pedida não tem modelo pronto. A API traduz em HTTP 503."""

    def __init__(
        self, tarefa: Tarefa, estado: EstadoModelo, detalhe: str | None = None
    ):
        self.tarefa = tarefa
        self.estado = estado
        self.retry_after = (
            SEGUNDOS_RETRY_CARREGANDO if estado == EstadoModelo.carregando else None
        )
        mensagens = {
            EstadoModelo.nao_carregado: "o modelo ainda não foi carregado",
            EstadoModelo.carregando: "o modelo está sendo carregado; tente novamente em instantes",
            EstadoModelo.falhou: f"a carga do modelo falhou ({detalhe})",
        }
        super().__init__(
            f"Tarefa '{tarefa.value}' indisponível: {mensagens.get(estado, estado)}."
        )


@dataclass
class SituacaoModelo:
    config: ModeloConfig
    estado: EstadoModelo = EstadoModelo.nao_carregado
    instancia: object | None = None
    erro: str | None = None
    segundos_carga: float | None = None
    carregado_em: datetime | None = None


def _fabrica_padrao(config: ModeloConfig, dispositivo: str):
    from src.ia.modelos_hf import criar_modelo

    return criar_modelo(config, dispositivo)


def _dispositivo_padrao() -> str:
    from src.ia.modelos_hf import escolher_dispositivo

    return escolher_dispositivo()


class GerenciadorModelos:
    def __init__(
        self,
        configs: dict[Tarefa, ModeloConfig] | None = None,
        dispositivo: str | None = None,
        fabrica: Callable[[ModeloConfig, str], object] | None = None,
    ):
        self.configs = configs or {t: catalogo.modelo_da_tarefa(t) for t in Tarefa}
        self.dispositivo = dispositivo  # resolvido na carga (exige torch)
        self._fabrica = fabrica or _fabrica_padrao
        # Uma situação por MODELO; tarefas que usam o mesmo modelo a compartilham.
        self._situacoes: dict[str, SituacaoModelo] = {}
        for config in self.configs.values():
            self._situacoes.setdefault(config.chave, SituacaoModelo(config))
        self._lock_inferencia = threading.Lock()
        self._lock_carga = threading.Lock()
        self._thread: threading.Thread | None = None

    # ── Carga ──

    def carregar(self, em_segundo_plano: bool = False) -> threading.Thread | None:
        if em_segundo_plano:
            self._thread = threading.Thread(
                target=self._carregar_todos, name="carga-modelos", daemon=True
            )
            self._thread.start()
            return self._thread
        self._carregar_todos()
        return None

    def aguardar_carga(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def _carregar_todos(self) -> None:
        with self._lock_carga:
            pendentes = [
                s for s in self._situacoes.values() if s.estado != EstadoModelo.pronto
            ]
            for situacao in pendentes:
                situacao.estado = EstadoModelo.carregando
            try:
                if self.dispositivo is None:
                    self.dispositivo = _dispositivo_padrao()
            except Exception as erro:  # noqa: BLE001 — ex.: torch não instalado
                for situacao in pendentes:
                    self._registrar_falha(situacao, erro)
                return
            for situacao in pendentes:
                self._carregar(situacao)

    def _carregar(self, situacao: SituacaoModelo) -> None:
        inicio = time.perf_counter()
        logger.info("Carregando %s em %s...", situacao.config.hf_id, self.dispositivo)
        try:
            instancia = self._fabrica(situacao.config, self.dispositivo)
            instancia.carregar()
        except Exception as erro:  # noqa: BLE001 — falha vira estado, não derruba a API
            self._registrar_falha(situacao, erro)
            return
        situacao.instancia = instancia
        situacao.segundos_carga = round(time.perf_counter() - inicio, 1)
        situacao.carregado_em = datetime.now().replace(microsecond=0)
        situacao.erro = None
        situacao.estado = EstadoModelo.pronto
        logger.info(
            "%s pronto em %.1fs.", situacao.config.chave, situacao.segundos_carga
        )

    @staticmethod
    def _registrar_falha(situacao: SituacaoModelo, erro: Exception) -> None:
        situacao.estado = EstadoModelo.falhou
        situacao.erro = f"{type(erro).__name__}: {erro}"[:300]
        logger.error("Falha ao carregar %s: %s", situacao.config.chave, situacao.erro)

    # ── Consulta de estado ──

    def situacao(self, tarefa: Tarefa) -> SituacaoModelo:
        return self._situacoes[self.configs[tarefa].chave]

    def estado(self, tarefa: Tarefa) -> EstadoModelo:
        return self.situacao(tarefa).estado

    def todas_prontas(self) -> bool:
        return all(s.estado == EstadoModelo.pronto for s in self._situacoes.values())

    def verificar(self, tarefa: Tarefa) -> None:
        """Levanta ModeloIndisponivel se a tarefa não puder ser executada agora."""
        self._instancia(tarefa)

    def _instancia(self, tarefa: Tarefa):
        situacao = self.situacao(tarefa)
        if situacao.estado != EstadoModelo.pronto:
            raise ModeloIndisponivel(tarefa, situacao.estado, situacao.erro)
        return situacao.instancia

    # ── Inferência ──

    def resumir(self, texto: str):
        modelo = self._instancia(Tarefa.resumo)
        with self._lock_inferencia:
            return modelo.resumir(texto)

    def classificar_tom(self, texto: str):
        modelo = self._instancia(Tarefa.tom)
        with self._lock_inferencia:
            return modelo.classificar(texto, catalogo.HIPOTESES_TOM)

    def avaliar_relevancia(self, texto: str, titulo: str | None = None):
        """Estratégia híbrida do catálogo: termo de GD no título OU hipótese zero-shot.

        Sem título (texto livre), vale a primeira linha do texto.
        """
        modelo = self._instancia(Tarefa.relevancia)
        with self._lock_inferencia:
            resultado = modelo.avaliar_hipotese(
                texto, catalogo.HIPOTESE_RELEVANCIA, catalogo.LIMIAR_RELEVANCIA
            )
        if titulo is None:
            titulo = (texto or "").strip().split("\n", 1)[0]
        por_termo = catalogo.termo_gd(titulo)
        resultado.por_termo_gd = por_termo
        resultado.relevante = bool(resultado.relevante or por_termo)
        return resultado

    def executar(self, tarefa: Tarefa, texto: str):
        acoes = {
            Tarefa.resumo: self.resumir,
            Tarefa.tom: self.classificar_tom,
            Tarefa.relevancia: self.avaliar_relevancia,
        }
        return acoes[tarefa](texto)
