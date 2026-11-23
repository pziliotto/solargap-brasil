"""
PROJETO: SolarGap Brasil
ARQUIVO: agente/agente.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026 (TP5)

DESCRIÇÃO:
    Agente inteligente de apoio à decisão (TP5, Opção 3 do enunciado). Recebe
    uma pergunta em português e devolve diagnóstico, fatores e recomendações
    sobre a lacuna entre o potencial solar residencial e a geração atual, com
    rastreabilidade de cada número.

CICLO (um "passo" de agente por pergunta):
    1. Perceber   localizar o recorte (UF/município) na pergunta; sem lugar
                  citado, herdar o recorte da conversa (memória).
    2. Planejar   o LLM escolhe as ferramentas (JSON); sem LLM, regras de
                  intenção por palavras-chave fazem o plano.
    3. Agir       executar as ferramentas sobre a Gold (ferramentas.py).
    4. Redigir    o LLM transforma os fatos em diagnóstico e recomendações;
                  sem LLM, um modelo de texto fixo organiza os mesmos fatos.
    5. Verificar  conferir se cada número da resposta veio dos fatos.

MODOS:
    "llm"     planejamento e redação pelo modelo (Ollama ou API);
    "regras"  sem modelo disponível, ou usar_llm=False. Mesmas ferramentas,
              mesmos números: muda só a redação. Garante a demonstração e
              serve de linha de base na avaliação (avaliacao.py).
    "misto"   o LLM caiu no meio (ex.: tempo esgotado na redação).

MEMÓRIA CONVERSACIONAL:
    Stateless no servidor: o cliente (painel ou API) envia o histórico e o
    contexto devolvido na resposta anterior. Assim a API escala sem sessão e
    o painel guarda a conversa em st.session_state.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field

from src.agente import ferramentas as fr
from src.agente import prompts
from src.agente.llm import ClienteLLM, LLMIndisponivel
from src.agente.recortes import Localizador, Recorte, normalizar
from src.agente.verificacao import verificar, verificar_rotulos
from src.servicos import dados
from src.servicos import potencial as svc
from src.servicos.indicadores import VISAO_PADRAO, normalizar_visao

MAX_FERRAMENTAS = 5
MAX_FATOS_MEMORIA = 40

# Intenções por palavras-chave (texto sem acento, minúsculo).
INTENCOES = {
    "oportunidades": ("investir", "investimento", "oportunidade", "priorizar", "prioridade",
                      "mercado", "expandir", "prospec", "melhores municipios", "onde atuar",
                      "onde vender", "onde abrir"),
    "explicacao": ("por que", "porque", "explica", "motivo", "fator", "barreira", "o que fazer",
                   "como aumentar", "acelerar", "recomend", "abaixo do esperado", "baixa adocao"),
    "cenarios": ("clima", "2030", "2040", "2050", "cenario", "futuro", "projec", "ssp",
                 "mudanca"),
    "comparacao": ("compar", "ranking", "versus", " vs ", "melhor estado", "pior estado",
                   "lider", "estados com"),
    "regulacao": ("icms", "imposto", "isencao", "lei", "14.300", "fio b", "regula", "noticia",
                  "aneel", "politica", "tarifa"),
}  # fmt: skip
TERMOS_NOTICIA = {
    "fio b": "fio B", "14.300": "14.300", "icms": "ICMS", "tarifa": "tarifa",
    "compartilhada": "compartilhada", "compensacao": "compensação", "sandbox": "sandbox",
}  # fmt: skip
PALAVRAS_BRASIL = ("brasil", "pais", "nacional")


@dataclass
class RespostaAgente:
    pergunta: str
    resposta: str
    modo: str
    modelo: str | None
    intencoes: list[str]
    recorte: dict
    recorte_herdado: bool
    ferramentas: list[dict]
    acoes: list[dict]
    fatos: list[str]
    verificacao: dict
    avisos: list[str] = field(default_factory=list)
    tempo_s: float = 0.0
    visao: str = VISAO_PADRAO

    @property
    def contexto(self) -> dict:
        """O que o cliente devolve na próxima pergunta (memória): o recorte e os
        fatos já consultados, para o LLM poder retomá-los e a verificação
        aceitá-los (são dados da Gold, não texto gerado)."""
        return {"recorte": self.recorte, "fatos": self.fatos[:MAX_FATOS_MEMORIA]}

    def como_dict(self) -> dict:
        return asdict(self) | {"contexto": self.contexto}


class Agente:
    def __init__(self, ctx: fr.Contexto, cliente: ClienteLLM | None = None):
        self.ctx = ctx
        self.cliente = cliente if cliente is not None else ClienteLLM()
        self.localizador = Localizador(ctx.base.municipal)

    @classmethod
    def carregar(cls, cliente: ClienteLLM | None = None) -> Agente:
        """Lê a Gold uma vez (DadosIndisponiveis se faltar arquivo obrigatório)."""
        ctx = fr.Contexto(
            base=svc.carregar_base(),
            agregado=dados.carregar_agregado(),
            dim_uf=dados.carregar_uf(),
            icms=dados.carregar_icms(),
            corpus=dados.carregar_corpus_completo(),
        )
        return cls(ctx, cliente)

    # ─────────── 1. perceber ───────────

    def _recorte(self, pergunta: str, contexto: dict | None) -> tuple[Recorte, bool]:
        recorte = self.localizador.localizar(pergunta)
        texto = normalizar(pergunta)
        explicito_brasil = any(p in re.findall(r"\w+", texto) for p in PALAVRAS_BRASIL)
        anterior = (contexto or {}).get("recorte") or {}
        if recorte.nivel == "brasil" and not explicito_brasil and anterior.get("nivel") in (
            "uf", "municipio",
        ):  # fmt: skip
            herdado = Recorte(
                uf=anterior.get("uf"),
                cod_ibge=anterior.get("cod_ibge"),
                nome_municipio=anterior.get("municipio"),
                ufs_citadas=[anterior["uf"]] if anterior.get("uf") else [],
            )
            return herdado, True
        return recorte, False

    # ─────────── 2. planejar ───────────

    @staticmethod
    def intencoes(pergunta: str) -> list[str]:
        texto = f" {normalizar(pergunta)} "
        achadas = [
            nome
            for nome, chaves in INTENCOES.items()
            if any(c in texto for c in chaves)
        ]
        return achadas or ["diagnostico"]

    @staticmethod
    def _termo_noticia(pergunta: str) -> str | None:
        texto = normalizar(pergunta)
        return next(
            (termo for chave, termo in TERMOS_NOTICIA.items() if chave in texto), None
        )

    def plano_por_regras(
        self, pergunta: str, recorte: Recorte, intencoes: list[str]
    ) -> list[dict]:
        alvo = (
            {"cod_ibge": recorte.cod_ibge} if recorte.cod_ibge else {"uf": recorte.uf}
        )
        plano: list[dict] = []

        def add(nome: str, **argumentos):
            passo = {"nome": nome, "argumentos": argumentos}
            if passo not in plano:
                plano.append(passo)

        for intencao in intencoes:
            if intencao == "diagnostico":
                add("resumo_potencial", **alvo)
                if recorte.nivel == "brasil":
                    add("comparar_ufs")
                    add("oportunidades", n=5)
                else:
                    add("explicar_gap", **alvo)
                    if recorte.nivel == "uf":
                        add("adocao_uf", uf=recorte.uf)
            elif intencao == "explicacao":
                add("resumo_potencial", **alvo)
                add("explicar_gap", **alvo)
            elif intencao == "oportunidades":
                add("resumo_potencial", **alvo)
                add("oportunidades", uf=recorte.uf, n=5)
                # "O que explica" precisa de fatos: fatores do recorte.
                add("explicar_gap", **alvo)
            elif intencao == "comparacao":
                add("comparar_ufs", ufs=recorte.ufs_citadas or None)
                for sigla in recorte.ufs_citadas[:2]:
                    add("explicar_gap", uf=sigla)
            elif intencao == "cenarios":
                add("resumo_potencial", **alvo)
                add("cenarios_climaticos", **alvo)
            elif intencao == "regulacao":
                add("noticias", termo=self._termo_noticia(pergunta), uf=recorte.uf, n=3)
                add("politica_icms", uf=recorte.uf)
        return plano[:MAX_FERRAMENTAS]

    def _validar_plano(self, bruto: dict, recorte: Recorte) -> list[dict]:
        """Mantém só ferramentas do catálogo e força o recorte localizado
        (o LLM pode errar o código IBGE; o localizador não)."""
        plano = []
        for passo in (bruto.get("ferramentas") or [])[:MAX_FERRAMENTAS]:
            if not isinstance(passo, dict) or passo.get("nome") not in fr.CATALOGO:
                continue
            argumentos = dict(passo.get("argumentos") or {})
            uf_pedida = str(argumentos.get("uf") or "").upper()
            if uf_pedida in recorte.ufs_citadas[1:] and not argumentos.get("cod_ibge"):
                # comparação: a segunda UF citada vale como está
                argumentos = {**argumentos, "uf": uf_pedida, "cod_ibge": None}
            elif "cod_ibge" in argumentos or "uf" in argumentos:
                argumentos["cod_ibge"] = recorte.cod_ibge
                argumentos["uf"] = recorte.uf
                if passo["nome"] in (
                    "oportunidades",
                    "politica_icms",
                    "adocao_uf",
                    "noticias",
                ):
                    argumentos.pop("cod_ibge")
            if passo["nome"] == "comparar_ufs":
                argumentos["ufs"] = recorte.ufs_citadas or None
            item = {"nome": passo["nome"], "argumentos": argumentos}
            if item not in plano:
                plano.append(item)
        return plano

    @staticmethod
    def _fatos_anteriores(
        contexto: dict | None, recorte: Recorte, herdado: bool, atuais: list[str]
    ) -> list[str]:
        """Fatos da pergunta anterior, só se a conversa segue no mesmo recorte."""
        contexto = contexto or {}
        anterior = contexto.get("recorte") or {}
        mesmo = herdado or (
            anterior.get("cod_ibge") == recorte.cod_ibge
            and anterior.get("uf") == recorte.uf
        )
        if not mesmo:
            return []
        return [
            f
            for f in contexto.get("fatos") or []
            if isinstance(f, str) and f not in atuais
        ][:MAX_FATOS_MEMORIA]

    # ─────────── 4. redigir sem LLM ───────────

    @staticmethod
    def redigir_por_regras(resultados: list[fr.ResultadoFerramenta], acoes: list[dict],
                           avisos: list[str]) -> str:  # fmt: skip
        por_nome: dict[str, list[str]] = {}
        for r in resultados:
            por_nome.setdefault(r.nome, []).extend(r.fatos)
        secoes = [
            ("Diagnóstico", ["resumo_potencial", "adocao_uf", "comparar_ufs"]),
            ("O que explica", ["explicar_gap"]),
            ("Onde priorizar", ["oportunidades"]),
            ("Cenários 2030–2050", ["cenarios_climaticos"]),
            ("Regulação e contexto", ["politica_icms", "noticias"]),
        ]
        partes = []
        vistos: set[str] = set()
        for titulo, nomes in secoes:
            fatos = [
                f
                for n in nomes
                for f in por_nome.get(n, [])
                if not (f in vistos or vistos.add(f))
            ]
            if fatos:
                partes.append(f"**{titulo}**\n" + "\n".join(f"- {f}" for f in fatos))
        bloco = Agente.recomendacoes(resultados, acoes)
        if bloco:
            partes.append(bloco)
        ressalvas = [
            *fr.FATOS_FIXOS,
            "Fatores do SHAP indicam associação, não causa.",
        ] + avisos
        partes.append("**Ressalvas**\n" + "\n".join(f"- {r}" for r in ressalvas))
        return "\n\n".join(partes)

    @staticmethod
    def recomendacoes(
        resultados: list[fr.ResultadoFerramenta], acoes: list[dict]
    ) -> str:
        """Seção de recomendações montada pelo código, nos dois modos.

        Na rodada 2 com o qwen2.5:7b, as recomendações escritas pelo modelo
        contradiziam a ação do fator ("compensar a baixa agropecuária com
        projetos rurais") ou saíam do alcance do negócio ("aumentar a renda").
        A escolha da ação é regra (ACOES_POR_FATOR); o texto também passou a
        ser, e o LLM fica com diagnóstico, explicação e ressalvas.
        """
        itens = []
        oportunidades = next((r for r in resultados if r.nome == "oportunidades"), None)
        if oportunidades and oportunidades.dados:
            nomes = ", ".join(
                f"{d['nome']} ({d['uf']})" for d in oportunidades.dados[:3]
            )
            itens.append(
                f"**Onde priorizar**: {nomes}, os maiores gaps acima do esperado pelo "
                "perfil. Antes de investir, peça a explicação de cada município para "
                "escolher o produto (financiamento, geração compartilhada, rural)."
            )
        recortes = list(dict.fromkeys(a.get("recorte") for a in acoes))
        varios = len(recortes) > 1
        # comparação: alterna entre os recortes para nenhum ficar sem ação
        filas = [[a for a in acoes if a.get("recorte") == r] for r in recortes]
        intercaladas = [fila[i] for i in range(max(map(len, filas), default=0))
                        for fila in filas if i < len(fila)]  # fmt: skip
        # mesma ação em mais de um recorte: um item só ("Densidade (RS e SC)")
        agrupadas: dict[str, dict] = {}
        for a in intercaladas:
            chave = a["acao"]
            if chave in agrupadas:
                agrupadas[chave]["recortes"].append(a.get("recorte"))
            else:
                agrupadas[chave] = {**a, "recortes": [a.get("recorte")]}
        for a in agrupadas.values():
            if len(itens) >= 4:
                break
            lugares = sorted({r for r in a["recortes"] if r}, key=recortes.index)
            rotulo = (
                f"{a['fator']} ({' e '.join(lugares)})"
                if varios and lugares
                else a["fator"]
            )
            itens.append(f"**{rotulo}**: {a['acao']}")
        if not itens:
            # sem barreira medida (cenários, ranking, regulação): passo seguinte
            # por ferramenta, para a seção nunca sumir (bug da rodada 3)
            nomes = {r.nome for r in resultados if not r.erro}
            padrao = [
                (
                    "cenarios_climaticos",
                    (
                        "**Clima**: usar a faixa de incerteza dos cenários no dimensionamento "
                        "dos sistemas; a prioridade de mercado não muda com o clima."
                    ),
                ),
                (
                    "comparar_ufs",
                    (
                        "**Entre estados**: pedir as oportunidades e os fatores de cada UF "
                        "antes de decidir onde atuar."
                    ),
                ),
                (
                    "politica_icms",
                    (
                        "**ICMS**: considerar a data de início da isenção no cálculo do retorno "
                        "e acompanhar mudanças no convênio estadual."
                    ),
                ),
                (
                    "noticias",
                    (
                        "**Regulação**: acompanhar as regras de compensação (Lei 14.300 e fio B) "
                        "ao projetar o retorno de novos sistemas."
                    ),
                ),
                (
                    "resumo_potencial",
                    (
                        "**Próximo passo**: pedir a explicação dos fatores e as oportunidades "
                        "deste recorte."
                    ),
                ),
            ]
            itens = [texto for nome, texto in padrao if nome in nomes][:3]
        if not itens:
            return ""
        return "**Recomendações**\n" + "\n".join(
            f"{i}. {t}" for i, t in enumerate(itens, 1)
        )

    @staticmethod
    def encaixar_recomendacoes(texto: str, bloco: str) -> str:
        """Troca a seção de recomendações do LLM (se ele escreveu uma) pelo bloco
        do código, antes das ressalvas. Aceita título em negrito ou em markdown
        com # (o modelo às vezes escreve "# Ressalvas" e o bloco ia para o fim)."""
        ressalvas = re.compile(
            r"\*\*Ressalvas\*\*|^[ \t]*#{1,6}[ \t]*Ressalvas\b", re.MULTILINE
        )
        recomendacoes = re.compile(
            r"(?:\*\*Recomenda[çc][õo]es\*\*|^[ \t]*#{1,6}[ \t]*Recomenda[çc][õo]es\b)"
            r".*?(?=" + ressalvas.pattern + r"|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        texto = recomendacoes.sub("", texto).strip()
        if not bloco:
            return texto
        marca = ressalvas.search(texto)
        if marca is None:
            return f"{texto}\n\n{bloco}"
        inicio = marca.start()
        return f"{texto[:inicio].rstrip()}\n\n{bloco}\n\n{texto[inicio:].lstrip()}"

    # ─────────── ciclo completo ───────────

    def perguntar(
        self, pergunta: str, historico: list[dict] | None = None, contexto: dict | None = None,
        visao: str = VISAO_PADRAO, usar_llm: bool = True,
    ) -> RespostaAgente:  # fmt: skip
        inicio = time.perf_counter()
        historico = historico or []
        self.ctx.visao = normalizar_visao(visao)
        avisos: list[str] = []

        recorte, herdado = self._recorte(pergunta, contexto)
        if recorte.homonimos:
            avisos.append(
                f"Há {len(recorte.homonimos)} municípios com esse nome; usei "
                f"{recorte.descricao}. Cite a UF para escolher outro "
                f"({', '.join(recorte.homonimos[1:4])})."
            )
        intencoes = self.intencoes(pergunta)

        llm_ok = usar_llm and self.cliente.ativo
        modo = "llm" if llm_ok else "regras"
        plano = []
        if llm_ok:
            try:
                bruto = self.cliente.conversar_json(
                    prompts.mensagens_planejamento(
                        pergunta, recorte.como_dict(), historico, fr.CATALOGO
                    ),
                    max_tokens=400,
                )
                plano = self._validar_plano(bruto, recorte)
                if isinstance(bruto.get("intencao"), str):
                    intencoes = list(dict.fromkeys([bruto["intencao"], *intencoes]))
            except LLMIndisponivel as erro:
                llm_ok, modo = False, "regras"
                avisos.append(
                    f"Modelo de linguagem indisponível ({erro}); resposta no modo por regras."
                )
        if not plano:
            plano = self.plano_por_regras(
                pergunta,
                recorte,
                [i for i in intencoes if i in INTENCOES] or ["diagnostico"],
            )

        resultados = [fr.executar(self.ctx, p["nome"], p["argumentos"]) for p in plano]
        fatos = list(dict.fromkeys(f for r in resultados for f in r.fatos))
        if fatos:
            fatos += fr.FATOS_FIXOS
        anteriores = self._fatos_anteriores(contexto, recorte, herdado, fatos)
        acoes = [
            a
            for r in resultados
            if r.nome == "explicar_gap"
            for a in r.dados.get("acoes", [])
        ]
        acoes = list({(a.get("recorte"), a["acao"]): a for a in acoes}.values())
        for r in resultados:
            if r.erro:
                avisos.append(f"{r.nome}: {r.erro}")
            aviso_visao = (
                r.dados.get("aviso_visao") if isinstance(r.dados, dict) else None
            )
            if aviso_visao and aviso_visao not in avisos:
                avisos.append(aviso_visao)

        resposta = None
        if llm_ok and fatos:
            try:
                resposta = self.cliente.conversar(
                    prompts.mensagens_redacao(
                        pergunta,
                        recorte.como_dict(),
                        fatos,
                        acoes,
                        historico,
                        avisos,
                        anteriores,
                    )
                )
                resposta = self.encaixar_recomendacoes(
                    resposta, self.recomendacoes(resultados, acoes)
                )
            except LLMIndisponivel as erro:
                modo = "misto"
                avisos.append(
                    f"A redação pelo modelo falhou ({erro}); texto no modo por regras."
                )
        if resposta is None:
            resposta = (
                self.redigir_por_regras(resultados, acoes, avisos)
                if fatos
                else "Não encontrei dados para responder. Cite uma UF ou um município."
            )

        checagem = verificar(resposta, fatos + anteriores, pergunta)
        for rotulo, numero_errado in verificar_rotulos(resposta, fatos + anteriores):
            avisos.append(
                f'O valor {numero_errado} aparece na resposta como "{rotulo}", mas nos '
                "dados ele tem outro significado. Confira na aba de evidências."
            )
        if checagem["nao_encontrados"]:
            avisos.append(
                "Números da resposta que não aparecem nos dados consultados: "
                + ", ".join(checagem["nao_encontrados"])
                + ". Confira na aba de evidências."
            )
        return RespostaAgente(
            pergunta=pergunta,
            resposta=resposta,
            modo=modo,
            modelo=self.cliente.config.descricao if modo != "regras" else None,
            intencoes=intencoes,
            recorte=recorte.como_dict(),
            recorte_herdado=herdado,
            ferramentas=[r.como_dict() for r in resultados],
            acoes=acoes,
            fatos=fatos,
            verificacao=checagem,
            avisos=avisos,
            tempo_s=round(time.perf_counter() - inicio, 2),
            visao=self.ctx.visao,
        )
