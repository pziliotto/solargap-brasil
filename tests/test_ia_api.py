"""Rotas de IA (TP4), processamento em lote e junção do enriquecimento ao corpus.

As rotas usam um gerenciador com fábrica falsa: os estados e erros (503, 504,
422, 404) são exercitados sem PyTorch e sem download. A inferência real é
coberta em test_ia.py, com modelos minúsculos.
"""

import threading
import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.dependencias import Repositorio, obter_repositorio
from src.api.main import app
from src.api.rotas.ia import obter_gerenciador
from src.ia import catalogo, processar_corpus
from src.ia.catalogo import Arquitetura, ModeloConfig, Tarefa
from src.ia.modelos_hf import (
    ResultadoClassificacao,
    ResultadoRelevancia,
    ResultadoResumo,
)
from src.ia.motor import GerenciadorModelos
from src.preparacao import esquema
from src.servicos import dados, noticias

TEXTO = (
    "A potência instalada de micro e minigeração distribuída solar no Brasil "
    "ultrapassou 40 GW, segundo a ANEEL, com Minas Gerais na liderança."
)


class ModeloFalso:
    atraso = 0.0

    def __init__(self, config, dispositivo):
        self.config = config

    def carregar(self):
        if self.config.chave == "quebrado":
            raise OSError("pesos ausentes")

    def resumir(self, texto):
        time.sleep(self.atraso)
        return ResultadoResumo(
            "Geração distribuída passa de 40 GW.", len(texto.split()), False
        )

    def classificar(self, texto, hipoteses):
        dist = {r: round(1 / len(hipoteses), 4) for r in hipoteses}
        return ResultadoClassificacao("favoravel", dist["favoravel"], dist, 30, False)

    def avaliar_hipotese(self, texto, hipotese, limiar):
        prob = 0.97 if "solar" in texto.lower() else 0.02
        return ResultadoRelevancia(prob >= limiar, prob, 30, False)


def _configs(chave_resumo="t5"):
    nli = ModeloConfig(
        "nli", "falso/nli", Arquitetura.nli, catalogo.TAREFAS_CLASSIFICACAO, "MIT", 512
    )
    t5 = ModeloConfig(
        chave_resumo,
        f"falso/{chave_resumo}",
        Arquitetura.seq2seq,
        (Tarefa.resumo,),
        "MIT",
        512,
    )
    return {Tarefa.resumo: t5, Tarefa.tom: nli, Tarefa.relevancia: nli}


def _gerenciador(carregar=True, **kwargs):
    gerenciador = GerenciadorModelos(
        _configs(**kwargs), dispositivo="cpu", fabrica=ModeloFalso
    )
    if carregar:
        gerenciador.carregar()
    return gerenciador


@pytest.fixture
def cliente_ia(tmp_path):
    estado = {"gerenciador": _gerenciador()}
    repositorio = Repositorio.carregar(pasta_external=tmp_path)
    app.dependency_overrides[obter_repositorio] = lambda: repositorio
    app.dependency_overrides[obter_gerenciador] = lambda: estado["gerenciador"]
    with TestClient(app) as cliente:
        cliente.estado = estado
        yield cliente
    app.dependency_overrides.clear()
    ModeloFalso.atraso = 0.0


# ═══════════════════ Rotas ═══════════════════


def test_processar_texto_padrao_resumo_e_relevancia(cliente_ia):
    resposta = cliente_ia.post("/processar_texto", json={"texto": TEXTO})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["tarefas"] == ["resumo", "relevancia"]
    assert corpo["resultados"]["resumo"]["resumo"].startswith("Geração")
    assert corpo["resultados"]["relevancia"]["relevante"] is True
    assert "tom" not in corpo["resultados"]  # não pedido, não aparece
    assert {m["tarefa"] for m in corpo["modelos"]} == {"resumo", "relevancia"}
    assert corpo["dispositivo"] == "cpu" and corpo["duracao_ms"] >= 0


def test_tom_vem_marcado_como_experimental(cliente_ia):
    corpo = cliente_ia.post(
        "/processar_texto", json={"texto": TEXTO, "tarefas": ["tom"]}
    ).json()
    tom = corpo["resultados"]["tom"]
    assert tom["experimental"] is True and "linha de base" in tom["aviso"]
    assert set(tom["distribuicao"]) == set(catalogo.ROTULOS_TOM)


@pytest.mark.parametrize(
    "payload",
    [
        {"texto": "curto demais"},
        {"texto": "palavra " * 3 + "x" * 60},  # caracteres suficientes, poucas palavras
        {"texto": TEXTO, "tarefas": []},
        {"texto": TEXTO, "tarefas": ["traducao"]},
        {"texto": "a" * 20_001},
    ],
)
def test_entrada_invalida_422(cliente_ia, payload):
    assert cliente_ia.post("/processar_texto", json=payload).status_code == 422


def test_modelo_carregando_503_com_retry_after(cliente_ia):
    liberar = threading.Event()

    class Lento(ModeloFalso):
        def carregar(self):
            liberar.wait(5)

    gerenciador = GerenciadorModelos(_configs(), dispositivo="cpu", fabrica=Lento)
    gerenciador.carregar(em_segundo_plano=True)
    cliente_ia.estado["gerenciador"] = gerenciador
    resposta = cliente_ia.post("/processar_texto", json={"texto": TEXTO})
    assert resposta.status_code == 503
    assert resposta.headers["retry-after"] == "30"
    assert "carregado" in resposta.json()["detail"]
    status = cliente_ia.get("/ia/status").json()
    assert status["pronto"] is False and status["tarefas"][0]["estado"] == "carregando"
    liberar.set()
    gerenciador.aguardar_carga(5)
    assert cliente_ia.post("/processar_texto", json={"texto": TEXTO}).status_code == 200


def test_falha_de_carga_503_sem_retry_e_isolada(cliente_ia):
    cliente_ia.estado["gerenciador"] = _gerenciador(chave_resumo="quebrado")
    resposta = cliente_ia.post("/processar_texto", json={"texto": TEXTO})
    assert resposta.status_code == 503 and "retry-after" not in resposta.headers
    assert "pesos ausentes" in resposta.json()["detail"]
    # A relevância usa outro modelo e continua funcionando
    ok = cliente_ia.post(
        "/processar_texto", json={"texto": TEXTO, "tarefas": ["relevancia"]}
    )
    assert ok.status_code == 200
    status = cliente_ia.get("/ia/status").json()
    estados = {t["tarefa"]: t["estado"] for t in status["tarefas"]}
    assert estados == {"resumo": "falhou", "tom": "pronto", "relevancia": "pronto"}


def test_nao_carregado_503(cliente_ia):
    cliente_ia.estado["gerenciador"] = _gerenciador(carregar=False)
    assert cliente_ia.post("/processar_texto", json={"texto": TEXTO}).status_code == 503


def test_timeout_504(cliente_ia, monkeypatch):
    monkeypatch.setenv("SOLARGAP_TIMEOUT_INFERENCIA", "0.2")
    ModeloFalso.atraso = 1.0
    resposta = cliente_ia.post(
        "/processar_texto", json={"texto": TEXTO, "tarefas": ["resumo"]}
    )
    assert (
        resposta.status_code == 504
        and "SOLARGAP_TIMEOUT_INFERENCIA" in resposta.json()["detail"]
    )


def test_processar_noticia_do_corpus(cliente_ia):
    id_noticia = dados.carregar_corpus()["id"].iloc[0]
    resposta = cliente_ia.post(
        f"/noticias/{id_noticia}/processar?tarefas=relevancia&tarefas=tom"
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["origem"] == f"noticia:{id_noticia}"
    assert set(corpo["resultados"]) == {"relevancia", "tom"}
    assert cliente_ia.post("/noticias/inexistente/processar").status_code == 404


def test_status_lista_as_tres_tarefas(cliente_ia):
    status = cliente_ia.get("/ia/status").json()
    assert status["pronto"] is True
    experimentais = {t["tarefa"] for t in status["tarefas"] if t["experimental"]}
    assert experimentais == {"tom"}


def test_raiz_lista_rotas_de_ia(cliente_ia):
    rotas = cliente_ia.get("/").json()["rotas"]
    assert "POST /processar_texto" in rotas and "GET /ia/status" in rotas


# ═══════════════════ Processamento em lote ═══════════════════


def test_lote_grava_incremental_e_respeita_troca_de_modelo(pasta_processed_temporaria):
    pasta = pasta_processed_temporaria
    (pasta / esquema.ARQUIVO_CORPUS_IA).unlink(missing_ok=True)
    total = len(dados.carregar_corpus(pasta))

    resultado = processar_corpus.executar(
        pasta, limite=3, gerenciador=_gerenciador(carregar=False)
    )
    assert len(resultado) == 3
    assert list(resultado.columns) == esquema.COLUNAS_CORPUS_IA

    # Segunda rodada: só as pendentes
    resultado = processar_corpus.executar(
        pasta, gerenciador=_gerenciador(carregar=False)
    )
    assert len(resultado) == total and resultado["id"].is_unique

    # Terceira rodada sem pendências: não carrega nada nem regrava
    gerenciador = _gerenciador(carregar=False)
    processar_corpus.executar(pasta, gerenciador=gerenciador)
    assert gerenciador.situacao(Tarefa.resumo).estado.value == "nao_carregado"

    # Outro modelo de resumo: tudo vira pendente de novo
    outro = processar_corpus.pendentes(
        dados.carregar_corpus(pasta),
        dados.carregar_corpus_ia(pasta),
        {"resumo": "outro/modelo", "relevancia": "falso/nli"},
        refazer=False,
    )
    assert len(outro) == total


def test_lote_falha_alto_se_modelo_nao_carrega(pasta_processed_temporaria):
    (pasta_processed_temporaria / esquema.ARQUIVO_CORPUS_IA).unlink(missing_ok=True)
    with pytest.raises(RuntimeError, match="não carregaram"):
        processar_corpus.executar(
            pasta_processed_temporaria,
            gerenciador=_gerenciador(carregar=False, chave_resumo="quebrado"),
        )


# ═══════════════════ Junção ao corpus ═══════════════════


def test_corpus_sem_arquivo_de_ia_tem_relevancia_nula(
    tmp_path, pasta_processed_temporaria
):
    (pasta_processed_temporaria / esquema.ARQUIVO_CORPUS_IA).unlink(missing_ok=True)
    corpus = dados.carregar_corpus_completo(pasta_processed_temporaria, tmp_path)
    assert corpus["relevante"].isna().all()


def test_corpus_com_ia_anexa_resumo_e_filtra_relevancia(
    tmp_path, pasta_processed_temporaria
):
    pasta = pasta_processed_temporaria
    ids = dados.carregar_corpus(pasta)["id"].head(3).tolist()
    pd.DataFrame(
        {
            "id": ids,
            "resumo": ["r1", "r2", "r3"],
            "resumo_truncado": [False, True, False],
            "relevante": [True, False, True],
            "relevancia_prob": [0.9, 0.1, 0.8],
            "modelo_resumo": "m",
            "modelo_relevancia": "n",
            "processado_em": "2026-11-16T10:00:00",
        }
    ).to_csv(pasta / esquema.ARQUIVO_CORPUS_IA, sep=";", index=False)

    corpus = dados.carregar_corpus_completo(pasta, tmp_path)
    assert corpus.set_index("id").loc[ids[0], "resumo"] == "r1"
    assert len(noticias.filtrar_noticias(corpus, relevante=True)) == 2
    assert (
        len(noticias.filtrar_noticias(corpus, relevante=False)) == 1
    )  # não avaliadas ficam de fora


def test_api_lista_noticias_com_relevancia(tmp_path, pasta_processed_temporaria):
    pasta = pasta_processed_temporaria
    id_relevante = dados.carregar_corpus(pasta)["id"].iloc[0]
    pd.DataFrame(
        {
            "id": [id_relevante],
            "resumo": ["resumo"],
            "relevante": [True],
            "relevancia_prob": [0.95],
        }
    ).to_csv(pasta / esquema.ARQUIVO_CORPUS_IA, sep=";", index=False)
    repositorio = Repositorio.carregar(pasta_processed=pasta, pasta_external=tmp_path)
    app.dependency_overrides[obter_repositorio] = lambda: repositorio
    try:
        with TestClient(app) as cliente:
            corpo = cliente.get("/noticias", params={"relevante": "true"}).json()
    finally:
        app.dependency_overrides.clear()
    assert corpo["total"] == 1
    item = corpo["itens"][0]
    assert (
        item["relevante"] is True
        and item["relevancia_prob"] == 0.95
        and item["resumo"] == "resumo"
    )


# ═══════════════════ Licença sem derivação (CC BY-ND, gov.br) ═══════════════════


def _id_da_fonte(fonte: str) -> str:
    corpus = dados.carregar_corpus()
    return corpus.loc[corpus["fonte"] == fonte, "id"].iloc[0]


def test_fontes_sem_derivacao_coincidem_com_o_cadastro():
    from src.data_acquisition.noticias.fontes import FONTES

    assert esquema.FONTES_SEM_DERIVACAO == {
        f.nome for f in FONTES if not f.permite_derivacao
    }
    assert esquema.permite_resumo("Agência Brasil") and not esquema.permite_resumo(
        "ANEEL"
    )


def test_anexar_ia_omite_resumo_das_fontes_cc_by_nd():
    corpus = pd.DataFrame(
        {
            "id": ["a", "b", "c"],
            "fonte": ["Agência Brasil", "ANEEL", "Agência Gov"],
            "resumo": [None] * 3,
        }
    )
    ia = pd.DataFrame(
        {
            "id": ["a", "b", "c"],
            "resumo": ["resumo A", "resumo B", "resumo C"],
            "resumo_truncado": [False, True, False],
            "relevante": ["True", "True", "False"],
            "relevancia_prob": [0.9, 0.8, 0.1],
        }
    )
    unido = dados.anexar_ia(corpus, ia).set_index("id")
    assert unido.loc["a", "resumo"] == "resumo A"
    assert unido.loc[["b", "c"], "resumo"].isna().all()
    assert unido.loc[["b", "c"], "resumo_truncado"].isna().all()
    assert bool(unido.loc["b", "relevante"])  # a classificação continua visível
    assert dados.anexar_ia(corpus.assign(resumo=["x", "y", "z"]), None)[
        "resumo"
    ].tolist() == [
        "x",
        None,
        None,
    ]


def test_api_lista_gov_br_sem_resumo(tmp_path):
    repositorio = Repositorio.carregar(pasta_external=tmp_path)
    app.dependency_overrides[obter_repositorio] = lambda: repositorio
    try:
        with TestClient(app) as cliente:
            for fonte in sorted(esquema.FONTES_SEM_DERIVACAO):
                corpo = cliente.get(
                    "/noticias", params={"fonte": fonte, "limite": 50}
                ).json()
                itens = corpo["itens"] if isinstance(corpo, dict) else corpo
                assert itens, fonte
                assert all(item.get("resumo") is None for item in itens), fonte
    finally:
        app.dependency_overrides.clear()


def test_processar_noticia_gov_br_sem_resumo(cliente_ia):
    id_aneel = _id_da_fonte("ANEEL")
    resposta = cliente_ia.post(f"/noticias/{id_aneel}/processar")
    assert resposta.status_code == 200
    assert set(resposta.json()["resultados"]) == {"relevancia"}  # padrão sem resumo
    pedido = cliente_ia.post(f"/noticias/{id_aneel}/processar?tarefas=resumo")
    assert pedido.status_code == 403 and "CC BY-ND" in pedido.json()["detail"]
    id_ab = _id_da_fonte("Agência Brasil")
    corpo = cliente_ia.post(f"/noticias/{id_ab}/processar").json()
    assert set(corpo["resultados"]) == {"resumo", "relevancia"}


def test_lote_nao_gera_resumo_para_gov_br():
    gerenciador = _gerenciador()
    corpus = dados.carregar_corpus()
    amostra = pd.concat(
        [
            corpus[corpus["fonte"] == f].head(1)
            for f in ("Agência Brasil", "ANEEL", "MME")
        ]
    )
    saida = processar_corpus.processar(amostra, gerenciador).set_index("id")
    linha = dict(zip(amostra["fonte"], amostra["id"]))
    assert saida.loc[linha["Agência Brasil"], "resumo"]
    assert pd.isna(saida.loc[linha["ANEEL"], "resumo"]) and pd.isna(
        saida.loc[linha["MME"], "resumo"]
    )
    assert saida["relevancia_prob"].notna().all()


# ═══════════════════ Relevância híbrida (benchmark v2, 22/11/2026) ═══════════════════


def test_relevancia_hibrida_termo_gd_no_titulo_ou_modelo():
    gerenciador = _gerenciador()
    assert catalogo.LIMIAR_RELEVANCIA == 0.4
    # O modelo falso dá 0,02 sem "solar": só a regra do título salva a notícia de GD.
    gd = gerenciador.avaliar_relevancia(
        "texto qualquer", titulo="ANEEL regulamenta a Lei 14.300"
    )
    assert gd.relevante and gd.por_termo_gd and gd.probabilidade < 0.4
    modelo = gerenciador.avaliar_relevancia(
        "Usina de energia solar", titulo="Usina nova"
    )
    assert modelo.relevante and not modelo.por_termo_gd
    fora = gerenciador.avaliar_relevancia(
        "Leilão de petróleo", titulo="Leilão de petróleo"
    )
    assert not fora.relevante and not fora.por_termo_gd
    # Termo de GD só no corpo não aciona a regra (ela olha o título).
    assert not gerenciador.avaliar_relevancia(
        "Leilão\n\nfala de minigeração", titulo="Leilão"
    ).relevante
    # Sem título: vale a primeira linha do texto.
    assert gerenciador.avaliar_relevancia("Regras da minigeração\n\ncorpo").por_termo_gd


def test_processar_texto_informa_regra_de_palavra(cliente_ia):
    corpo = cliente_ia.post(
        "/processar_texto",
        json={
            "texto": "Aneel revisa regras da micro e minigeração distribuída.",
            "tarefas": ["relevancia"],
        },
    ).json()
    relevancia = corpo["resultados"]["relevancia"]
    assert relevancia["relevante"] and relevancia["por_termo_gd"]
    assert relevancia["limiar"] == 0.4


def test_lote_grava_regra_e_estrategia():
    corpus = dados.carregar_corpus()
    saida = processar_corpus.processar(corpus.head(3), _gerenciador())
    assert "relevancia_por_termo" in saida.columns
    assert saida["modelo_relevancia"].str.endswith(catalogo.ESTRATEGIA_RELEVANCIA).all()
