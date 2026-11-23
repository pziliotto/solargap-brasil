"""Agente de apoio à decisão (TP5): localizador, ferramentas, planos, LLM
simulado, memória e verificação de números. Sem rede: o Ollama é imitado com
httpx.MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest

from src.agente import ferramentas as fr
from src.agente.agente import Agente
from src.agente.llm import ClienteLLM, ConfigLLM, LLMIndisponivel, extrair_json
from src.agente.recortes import Localizador
from src.agente.verificacao import extrair_numeros, verificar, verificar_rotulos

CAXIAS = "4305108"


@pytest.fixture(scope="module")
def agente_regras():
    return Agente.carregar(cliente=ClienteLLM(ConfigLLM(provedor="nenhum")))


@pytest.fixture(scope="module")
def localizador(agente_regras):
    return agente_regras.localizador


# ─────────── localizador ───────────


@pytest.mark.parametrize(
    ("pergunta", "descricao"),
    [
        ("Por que Caxias do Sul está abaixo do esperado?", "Caxias do Sul (RS)"),
        ("Onde investir no Rio Grande do Sul?", "Rio Grande do Sul"),
        ("O que explica o gap em Pará de Minas?", "Pará de Minas (MG)"),
        ("Rio Grande, no RS", "Rio Grande (RS)"),
        ("Como está o interior gaúcho?", "Rio Grande do Sul"),
        ("Bom Jesus no RS", "Bom Jesus (RS)"),
        ("e se a gente bater palmas", "Brasil"),
        ("Qual o potencial do Brasil?", "Brasil"),
    ],
)
def test_localizador(localizador: Localizador, pergunta, descricao):
    assert localizador.localizar(pergunta).descricao == descricao


def test_homonimo_sem_uf_avisa(localizador):
    recorte = localizador.localizar("Qual a situação de Bom Jesus?")
    assert len(recorte.homonimos) == 5 and recorte.cod_ibge is not None


def test_siglas_minusculas_nao_viram_uf(localizador):
    assert localizador.localizar("se to ma pa").ufs_citadas == []


# ─────────── ferramentas ───────────


def test_todas_as_ferramentas_rodam(agente_regras):
    ctx = agente_regras.ctx
    for nome in fr.CATALOGO:
        resultado = fr.executar(ctx, nome, {"uf": "RS", "cod_ibge": None})
        assert resultado.erro is None, (nome, resultado.erro)
        assert resultado.fatos, nome
        json.dumps(resultado.como_dict())  # serializável para a API


def test_ferramenta_descarta_argumento_inventado(agente_regras):
    resultado = fr.executar(
        agente_regras.ctx, "politica_icms", {"uf": "RS", "inventado": 1}
    )
    assert resultado.erro is None and "inventado" not in resultado.argumentos


def test_ferramenta_inexistente_e_uf_invalida(agente_regras):
    assert fr.executar(agente_regras.ctx, "apagar_tudo", {}).erro
    assert (
        "não encontrada"
        in fr.executar(agente_regras.ctx, "explicar_gap", {"uf": "XX"}).erro
    )


def test_oportunidades_ordenadas_e_coerentes(agente_regras):
    tabela = fr.tabela_oportunidades(agente_regras.ctx.base, "corrigida", "RS")
    gap = tabela["gap_acima_esperado_mwh_ano"]
    assert gap.is_monotonic_decreasing and (gap >= 0).all()
    assert (tabela["domicilios"] >= 5000).all()
    linha = tabela.iloc[0]
    esperado = (
        max(0, linha["taxa_prevista"] - linha["taxa_realizacao"]) * linha["x_mwh_ano"]
    )
    assert linha["gap_acima_esperado_mwh_ano"] == pytest.approx(esperado)


def test_acao_depende_do_nivel_do_fator(agente_regras):
    """Em Caxias do Sul a densidade reduz a taxa por ser ALTA: a ação é a de
    apartamentos e condomínios, não a de município espalhado."""
    acoes = fr.executar(agente_regras.ctx, "explicar_gap", {"cod_ibge": CAXIAS}).dados[
        "acoes"
    ]
    densidade = next(a for a in acoes if a["fator"] == "Densidade demográfica")
    assert densidade["nivel"] == "alto" and "condomínios" in densidade["acao"]


# ─────────── modo por regras ───────────


@pytest.mark.parametrize(
    ("pergunta", "intencao", "ferramenta"),
    [
        ("Onde investir no Paraná?", "oportunidades", "oportunidades"),
        ("Por que Recife adota pouco?", "explicacao", "explicar_gap"),
        ("Como fica Recife em 2050?", "cenarios", "cenarios_climaticos"),
        ("Compare RS e SC", "comparacao", "comparar_ufs"),
        ("O que dizem as notícias sobre o fio B?", "regulacao", "noticias"),
        ("Como está Santa Catarina?", "diagnostico", "resumo_potencial"),
    ],
)
def test_plano_por_regras(agente_regras, pergunta, intencao, ferramenta):
    resposta = agente_regras.perguntar(pergunta)
    assert resposta.modo == "regras" and intencao in resposta.intencoes
    assert ferramenta in [f["nome"] for f in resposta.ferramentas]
    assert resposta.verificacao["taxa"] == 1.0, resposta.verificacao


def test_memoria_herda_recorte(agente_regras):
    primeira = agente_regras.perguntar("Por que Caxias do Sul está abaixo do esperado?")
    seguinte = agente_regras.perguntar(
        "E os cenários climáticos?",
        [{"pergunta": primeira.pergunta, "resposta": primeira.resposta}],
        primeira.contexto,
    )
    assert seguinte.recorte_herdado and seguinte.recorte["cod_ibge"] == CAXIAS
    nacional = agente_regras.perguntar("E no Brasil?", [], primeira.contexto)
    assert not nacional.recorte_herdado and nacional.recorte["nivel"] == "brasil"


def test_visao_aneel_avisa_sobre_o_modelo(agente_regras):
    resposta = agente_regras.perguntar("Por que Curitiba adota pouco?", visao="aneel")
    assert resposta.visao == "aneel"
    assert any("visão corrigida" in aviso for aviso in resposta.avisos)


# ─────────── verificação ───────────


def test_extrair_numeros_pt_br():
    texto = (
        "Taxa de 9,0% e gap de 603,4 GWh/ano em 184.843 domicílios; Lei 14.300 de 2022."
    )
    assert extrair_numeros(texto) == ["9,0", "603,4", "184.843"]


def test_verificacao_acusa_numero_inventado():
    fatos = ["Caxias do Sul (RS): taxa de realização de 9,0%."]
    assert verificar("A taxa é 9,0%.", fatos)["taxa"] == 1.0
    resultado = verificar("A taxa é 9,0% e deve chegar a 25,0%.", fatos)
    assert resultado["nao_encontrados"] == ["25,0"] and resultado["taxa"] == 0.5


# ─────────── LLM simulado (Ollama) ───────────


def ollama_falso(plano: dict | str, resposta: str, chamadas: list):
    def tratar(requisicao: httpx.Request) -> httpx.Response:
        if requisicao.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}]})
        corpo = json.loads(requisicao.content)
        chamadas.append(corpo)
        if corpo.get("format") == "json":
            conteudo = plano if isinstance(plano, str) else json.dumps(plano)
        else:
            conteudo = resposta
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": conteudo}}
        )

    return httpx.MockTransport(tratar)


def agente_com_llm(agente_regras, plano, resposta, chamadas) -> Agente:
    cliente = ClienteLLM(
        ConfigLLM(provedor="ollama"), transporte=ollama_falso(plano, resposta, chamadas)
    )
    agente = Agente(agente_regras.ctx, cliente)
    agente.localizador = agente_regras.localizador
    return agente


def test_llm_planeja_e_redige(agente_regras):
    chamadas: list = []
    plano = {
        "intencao": "explicacao",
        "ferramentas": [
            {
                "nome": "resumo_potencial",
                "argumentos": {"cod_ibge": "9999999"},
            },  # código errado
            {"nome": "explicar_gap", "argumentos": {"cod_ibge": CAXIAS}},
            {"nome": "ferramenta_que_nao_existe", "argumentos": {}},
        ],
    }
    texto = "**Diagnóstico** Caxias do Sul realiza 9,0% do potencial; o modelo esperaria 10,8%."
    agente = agente_com_llm(agente_regras, plano, texto, chamadas)
    assert agente.cliente.disponivel()
    resposta = agente.perguntar("Por que Caxias do Sul está abaixo do esperado?")
    assert resposta.modo == "llm" and resposta.resposta.startswith(texto)
    assert "**Recomendações**" in resposta.resposta  # acrescentadas pelo código
    nomes = [f["nome"] for f in resposta.ferramentas]
    assert nomes == ["resumo_potencial", "explicar_gap"]  # inventada descartada
    assert (
        resposta.ferramentas[0]["argumentos"]["cod_ibge"] == CAXIAS
    )  # código corrigido
    assert resposta.verificacao["taxa"] == 1.0
    assert len(chamadas) == 2 and chamadas[0]["options"]["temperature"] == 0.0
    assert "9,0%" in chamadas[1]["messages"][1]["content"]  # os fatos chegam ao redator


def test_llm_com_numero_inventado_gera_aviso(agente_regras):
    plano = {"ferramentas": [{"nome": "resumo_potencial", "argumentos": {"uf": "RS"}}]}
    agente = agente_com_llm(
        agente_regras, plano, "O RS realiza 14,0% e vai dobrar para 28,0%.", []
    )
    resposta = agente.perguntar("Como está o RS?")
    assert resposta.verificacao["nao_encontrados"] == ["28,0"]
    assert any("28,0" in aviso for aviso in resposta.avisos)


def test_plano_invalido_cai_nas_regras(agente_regras):
    agente = agente_com_llm(agente_regras, "isto não é JSON", "texto", [])
    resposta = agente.perguntar("Onde investir no Paraná?")
    assert resposta.modo == "regras"
    assert "oportunidades" in [f["nome"] for f in resposta.ferramentas]
    assert any("indisponível" in aviso for aviso in resposta.avisos)


def test_llm_fora_do_ar_nao_quebra(agente_regras):
    def recusar(requisicao):
        raise httpx.ConnectError("conexão recusada", request=requisicao)

    cliente = ClienteLLM(
        ConfigLLM(provedor="ollama"), transporte=httpx.MockTransport(recusar)
    )
    agente = Agente(agente_regras.ctx, cliente)
    assert not cliente.disponivel()
    resposta = agente.perguntar("Por que Caxias do Sul está abaixo do esperado?")
    assert resposta.modo == "regras" and "Diagnóstico" in resposta.resposta


def test_extrair_json_tolera_prosa():
    assert extrair_json('Claro! {"a": 1} Espero ter ajudado.') == {"a": 1}
    with pytest.raises(LLMIndisponivel):
        extrair_json("sem objeto nenhum")


# ─────────── correções da rodada com o LLM real (22/11/2026) ───────────


def test_comparacao_traz_conclusao_pela_taxa(agente_regras):
    """O qwen2.5:7b disse que SC era "mais eficiente" por ter gap menor."""
    fatos = fr.executar(agente_regras.ctx, "comparar_ufs", {"ufs": ["SC", "RS"]}).fatos
    conclusao = next(f for f in fatos if f.startswith("Conclusão"))
    assert conclusao.startswith("Conclusão da comparação: RS aproveita melhor")
    assert "14,0% contra 12,7%, diferença de 1,3 p.p." in conclusao


def test_cenarios_dizem_que_clima_nao_explica_o_gap(agente_regras):
    fatos = fr.executar(
        agente_regras.ctx, "cenarios_climaticos", {"cod_ibge": CAXIAS}
    ).fatos
    assert any("não explica o gap de hoje" in f for f in fatos)


def test_oportunidades_trazem_criterio_e_fatores(agente_regras):
    resposta = agente_regras.perguntar("Onde investir no Rio Grande do Sul?")
    assert [f["nome"] for f in resposta.ferramentas] == [
        "resumo_potencial", "oportunidades", "explicar_gap",
    ]  # fmt: skip
    assert any(f.startswith("Critério do ranking") for f in resposta.fatos)


def test_plano_do_llm_mantem_a_segunda_uf_da_comparacao(agente_regras):
    plano = {
        "ferramentas": [
            {"nome": "comparar_ufs", "argumentos": {"ufs": ["RS", "SC"]}},
            {"nome": "explicar_gap", "argumentos": {"uf": "RS"}},
            {"nome": "explicar_gap", "argumentos": {"uf": "SC"}},
        ]
    }
    agente = agente_com_llm(agente_regras, plano, "Texto.", [])
    resposta = agente.perguntar("Compare RS e SC")
    ufs = [
        f["argumentos"].get("uf")
        for f in resposta.ferramentas
        if f["nome"] == "explicar_gap"
    ]
    assert ufs == ["RS", "SC"]


def test_numero_da_pergunta_anterior_e_aceito_e_vai_ao_redator(agente_regras):
    """Na avaliação, o LLM citou 9,1% (taxa de Bento Gonçalves) na pergunta de
    seguimento sobre cenários: número certo, mas de fora dos fatos do turno."""
    primeira = agente_regras.perguntar("Como está Bento Gonçalves?")
    taxa = next(f for f in primeira.fatos if "taxa de realização" in f)
    assert "9,1%" in taxa
    chamadas: list = []
    plano = {
        "ferramentas": [
            {"nome": "cenarios_climaticos", "argumentos": {"cod_ibge": "x"}}
        ]
    }
    agente = agente_com_llm(
        agente_regras, plano, "A taxa segue em 9,1%; o clima pouco muda.", chamadas
    )
    seguinte = agente.perguntar(
        "E os cenários climáticos?",
        [{"pergunta": primeira.pergunta, "resposta": primeira.resposta}],
        primeira.contexto,
    )
    assert seguinte.recorte_herdado and seguinte.verificacao["taxa"] == 1.0
    prompt_redator = chamadas[1]["messages"][1]["content"]
    assert "FATOS DA PERGUNTA ANTERIOR" in prompt_redator and taxa in prompt_redator
    assert primeira.resposta[:40] not in prompt_redator  # respostas antigas não entram


def test_fatos_anteriores_nao_valem_em_outro_recorte(agente_regras):
    primeira = agente_regras.perguntar("Como está Bento Gonçalves?")
    agente = agente_com_llm(
        agente_regras,
        {"ferramentas": [{"nome": "resumo_potencial", "argumentos": {"uf": "SC"}}]},
        "Em SC, a taxa é a mesma de Bento: 9,1%.",
        [],
    )
    resposta = agente.perguntar("E Santa Catarina?", [], primeira.contexto)
    assert "9,1" in resposta.verificacao["nao_encontrados"]


# ─────────── correções da rodada 2 com o LLM real (22/11/2026) ───────────


def test_percentual_do_gap_vem_pronto(agente_regras):
    """O qwen2.5:7b calculou 603,4 / 662,9 como 90,5% e 91,1% (certo: 91,0%)."""
    fatos = fr.executar(
        agente_regras.ctx, "resumo_potencial", {"cod_ibge": CAXIAS}
    ).fatos
    assert "O gap equivale a 91,0% do potencial." in fatos[0]


def test_recomendacoes_do_llm_sao_trocadas_pelas_do_codigo(agente_regras):
    texto = (
        "**Diagnóstico** RS e SC.\n\n**O que explica** Fatores.\n\n"
        "**Recomendações**\n- Aumentar a renda média da população.\n\n"
        "**Ressalvas** Associação, não causalidade."
    )
    plano = {
        "ferramentas": [
            {"nome": "comparar_ufs", "argumentos": {"ufs": ["RS", "SC"]}},
            {"nome": "explicar_gap", "argumentos": {"uf": "RS"}},
            {"nome": "explicar_gap", "argumentos": {"uf": "SC"}},
        ]
    }
    resposta = (
        agente_com_llm(agente_regras, plano, texto, [])
        .perguntar("Compare RS e SC")
        .resposta
    )
    assert "Aumentar a renda" not in resposta
    assert resposta.count("**Recomendações**") == 1
    assert resposta.index("**Recomendações**") < resposta.index("**Ressalvas**")
    bloco = resposta[
        resposta.index("**Recomendações**") : resposta.index("**Ressalvas**")
    ]
    assert "RS" in bloco and "SC" in bloco  # ações das duas UFs


def test_recomendacoes_de_oportunidades_comecam_pelo_ranking(agente_regras):
    resposta = agente_regras.perguntar("Onde investir no Rio Grande do Sul?").resposta
    assert (
        "1. **Onde priorizar**: Bagé (RS), Viamão (RS), Caxias do Sul (RS)" in resposta
    )


def test_verificacao_pega_rotulo_trocado(agente_regras):
    """r3 da rodada 2 chamou o gap total (603,4) de gap acima do esperado (12,2)."""
    fatos = agente_regras.perguntar("Onde investir no Rio Grande do Sul?").fatos
    errado = "Caxias do Sul tem 603,4 GWh/ano de gap acima do esperado."
    certo = "Caxias do Sul tem gap acima do esperado de 12,2 GWh/ano e gap de 603,4 GWh/ano."
    assert verificar_rotulos(errado, fatos) == [("acima do esperado", "603,4")]
    assert verificar_rotulos(certo, fatos) == []


def test_rotulos_sem_falso_alarme_nas_respostas_por_regras(agente_regras):
    from src.agente.avaliacao import avaliar

    tabela = avaliar(agente_regras, usar_llm=False)
    for linha in tabela.itertuples():
        resposta = agente_regras.perguntar(linha.pergunta)
        assert verificar_rotulos(resposta.resposta, resposta.fatos) == [], (
            linha.pergunta
        )


def test_ordinal_nao_e_numero():
    assert extrair_numeros("1º Bagé (RS): taxa de 4,9%") == ["4,9"]


# ─────────── correções da rodada 3 com o LLM real (23/11/2026) ───────────


@pytest.mark.parametrize(
    "pergunta",
    [
        "Como fica o potencial de Recife nos cenários até 2050?",
        "Quais estados têm as maiores taxas de realização?",
        "O que dizem as notícias sobre o fio B?",
        "Desde quando a Bahia tem isenção de ICMS na geração distribuída?",
        "Como está Mato Grosso?",
    ],
)
def test_toda_resposta_tem_recomendacoes(agente_regras, pergunta):
    """Na rodada 3, 6 de 15 respostas saíram sem a seção: sem ação de fator,
    encaixar_recomendacoes apagava a do LLM e não punha nada."""
    resposta = agente_regras.perguntar(pergunta).resposta
    assert "**Recomendações**" in resposta


def test_recomendacoes_do_llm_nunca_somem(agente_regras):
    plano = {
        "ferramentas": [
            {"nome": "cenarios_climaticos", "argumentos": {"cod_ibge": "x"}}
        ]
    }
    texto = "**Diagnóstico** Varia pouco.\n\n**Recomendações**\n- Algo.\n\n**Ressalvas** Cenário."
    resposta = (
        agente_com_llm(agente_regras, plano, texto, [])
        .perguntar("Como fica Recife em 2050?")
        .resposta
    )
    assert "**Clima**" in resposta and "Algo." not in resposta


def test_formato_do_prompt_sem_numeros_para_copiar():
    """O modelo copiou "2 ou 3 frases" e "1 ou 2 frases" na resposta."""
    from src.agente.prompts import SISTEMA_REDATOR

    formato = SISTEMA_REDATOR[SISTEMA_REDATOR.index("FORMATO") :]
    assert extrair_numeros(formato) == []


def test_contagem_perto_do_rotulo_nao_e_falso_alarme(agente_regras):
    fatos = agente_regras.perguntar("Onde investir no Rio Grande do Sul?").fatos
    texto = "No RS, 66 municípios com gap acima do esperado somam 199,4 GWh/ano."
    assert verificar_rotulos(texto, fatos) == []
    assert verificar_rotulos("O gap acima do esperado é de -1,8 p.p.", fatos) == [
        ("acima do esperado", "-1,8")
    ]


def test_fato_diz_se_esta_acima_da_media(agente_regras):
    """r1 da rodada 3: "14,0%, abaixo da média brasileira de 10,4%"."""
    fatos = fr.executar(agente_regras.ctx, "resumo_potencial", {"uf": "RS"}).fatos
    assert "(Brasil: 10,4%; acima da média nacional)" in fatos[1]


def test_acao_igual_em_duas_ufs_vira_um_item(agente_regras):
    resposta = agente_regras.perguntar("Compare RS e SC").resposta
    assert resposta.count("Densidade alta indica") == 1
    assert "**Densidade demográfica (RS e SC)**" in resposta


def test_recomendacoes_com_titulos_markdown():
    """Rodada 3.1: o modelo usou "# Ressalvas" e o bloco do código foi parar
    depois das ressalvas."""
    texto = (
        "# Diagnóstico\nTaxa baixa.\n\n# O que explica\nDensidade.\n\n"
        "## Recomendações\n- Do modelo.\n\n# Ressalvas\nAssociação."
    )
    bloco = "**Recomendações**\n1. **Clima**: do código."
    resposta = Agente.encaixar_recomendacoes(texto, bloco)
    assert "Do modelo." not in resposta
    assert resposta.count("Recomendações") == 1
    assert resposta.index("**Recomendações**") < resposta.index("# Ressalvas")
    assert resposta.index("# O que explica") < resposta.index("**Recomendações**")


def test_rotulo_em_pontos_percentuais_e_sem_percentual(agente_regras):
    """ "pontos percentuais" por extenso escapava; o % da taxa esperada colado
    ao rótulo gerava falso alarme (Pará de Minas)."""
    fatos = agente_regras.perguntar(
        "Por que Caxias do Sul está abaixo do esperado?"
    ).fatos
    assert verificar_rotulos(
        "O gap acima do esperado é de -4,3 pontos percentuais.", fatos
    ) == [("acima do esperado", "-4,3")]
    assert (
        verificar_rotulos(
            "A taxa esperada seria de 12,6%, gerando um gap acima do esperado.", fatos
        )
        == []
    )


def test_fato_de_explicacao_diz_o_sentido(agente_regras):
    """Mato Grosso (47,5% contra 44,7% esperada) foi descrito como "abaixo do
    esperado"; o fato passa a dizer o sentido."""
    fato = fr.executar(agente_regras.ctx, "explicar_gap", {"uf": "MT"}).fatos[0]
    assert "p.p.; acima do esperado)" in fato
    fato_caxias = fr.executar(
        agente_regras.ctx, "explicar_gap", {"cod_ibge": CAXIAS}
    ).fatos[0]
    assert "p.p.; abaixo do esperado)" in fato_caxias
