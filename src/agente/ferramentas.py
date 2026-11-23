"""
PROJETO: SolarGap Brasil
ARQUIVO: agente/ferramentas.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 22/11/2026 (TP5)

DESCRIÇÃO:
    Ferramentas do agente: consultas determinísticas sobre a camada Gold,
    reaproveitando src/servicos (o mesmo código do painel e da API). Nenhuma
    ferramenta chama o LLM e nenhuma calcula número novo fora das regras já
    documentadas no projeto, exceto o "gap acima do esperado" (ver abaixo).

CONTRATO:
    Cada ferramenta devolve um ResultadoFerramenta com:
        fatos  frases curtas, com os números já formatados em pt-BR. São o
               ÚNICO material que o LLM pode citar (prompts.py) e a base da
               verificação de números (verificacao.py);
        dados  o resultado bruto, para a API e para os gráficos do painel.

GAP ACIMA DO ESPERADO (ferramenta oportunidades):
    O modelo explicativo da Tarefa 4 prevê a taxa de realização que o perfil
    do município sugere (renda, tarifa, urbanização, agro, ICMS...). Quando a
    taxa observada fica abaixo da prevista, a diferença é adoção que o perfil
    "comportaria" e não aconteceu:
        gap_acima_do_esperado = max(0, prevista - observada) x potencial (x)
    em MWh/ano. É o critério de priorização de mercado: municípios grandes,
    com perfil favorável e adoção atrasada. Leitura de associação, não de
    causa: o modelo não mede o efeito de uma ação.

RECOMENDAÇÕES:
    Regras explícitas (ACOES_POR_FATOR), uma por família de fator SHAP que
    puxa a taxa para baixo. O LLM redige, mas não inventa a ação: escolhe
    entre as que a ferramenta devolveu.
"""

from __future__ import annotations

import inspect
import math
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from src.servicos import indicadores
from src.servicos import potencial as svc
from src.servicos.noticias import filtrar_noticias

# ═══════════════════ Formatação pt-BR ═══════════════════


def numero(valor: float, casas: int = 0) -> str:
    if valor is None or pd.isna(valor):
        return "sem dado"
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(valor: float, casas: int = 1) -> str:
    return (
        "sem dado"
        if valor is None or pd.isna(valor)
        else f"{numero(valor * 100, casas)}%"
    )


def energia(mwh: float) -> str:
    if mwh is None or pd.isna(mwh):
        return "sem dado"
    if abs(mwh) >= 1e6:
        return f"{numero(mwh / 1e6, 1)} TWh/ano"
    if abs(mwh) >= 1e3:
        return f"{numero(mwh / 1e3, 1)} GWh/ano"
    return f"{numero(mwh, 0)} MWh/ano"


# Premissas fixas do potencial (Tarefa 2): entram em toda resposta como fato,
# para que o LLM possa citá-las e a verificação as reconheça.
FATOS_FIXOS = [
    (
        "Premissas do potencial técnico residencial: 15 m² úteis de telhado por "
        "domicílio, eficiência do painel de 20% e performance ratio de 0,75; base "
        "ANEEL de 10/2026 (2026 parcial, até outubro)."
    ),
]

# ═══════════════════ Contrato ═══════════════════


@dataclass
class ResultadoFerramenta:
    nome: str
    argumentos: dict
    fatos: list[str]
    dados: dict | list = field(default_factory=dict)
    erro: str | None = None

    def como_dict(self) -> dict:
        return {
            "nome": self.nome,
            "argumentos": limpar(self.argumentos),
            "fatos": self.fatos,
            "dados": limpar(self.dados),
            "erro": self.erro,
        }


def limpar(valor):
    """Tipos do numpy/pandas para tipos do Python; NaN vira None (JSON válido)."""
    if isinstance(valor, dict):
        return {str(k): limpar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [limpar(v) for v in valor]
    if hasattr(valor, "item") and not isinstance(valor, (str, bytes)):
        valor = valor.item()
    if isinstance(valor, pd.Timestamp):
        return valor.isoformat()
    if isinstance(valor, float) and (math.isnan(valor) or math.isinf(valor)):
        return None
    return valor


@dataclass
class Contexto:
    """Dados que as ferramentas consultam (lidos uma vez, como na API)."""

    base: svc.BasePotencial
    agregado: pd.DataFrame | None = None
    dim_uf: pd.DataFrame | None = None
    icms: pd.DataFrame | None = None
    corpus: pd.DataFrame | None = None
    visao: str = indicadores.VISAO_PADRAO


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    descricao: str  # vai para o prompt de planejamento
    funcao: Callable[..., ResultadoFerramenta]
    parametros: str  # descrição curta dos argumentos, para o prompt


def _rotulo(uf: str | None, cod_ibge: str | None, base: svc.BasePotencial) -> str:
    if cod_ibge:
        linha = svc.linha_municipio(base, cod_ibge)
        return f"{linha['nome']} ({linha['uf']})"
    return uf or "Brasil"


# ═══════════════════ Ferramentas ═══════════════════


def resumo_potencial(
    ctx: Contexto, uf: str | None = None, cod_ibge: str | None = None
) -> ResultadoFerramenta:
    """Potencial (x), produção (y), gap e taxa de realização do recorte."""
    r = svc.resumo_recorte(ctx.base, ctx.visao, uf=uf, cod_ibge=cod_ibge)
    brasil = svc.resumo_recorte(ctx.base, ctx.visao)
    fatos = [
        (
            f"{r['nome']}: potencial técnico residencial de {energia(r['x_mwh_ano'])}, "
            f"produção estimada de {energia(r['y_mwh_ano'])} e gap de "
            f"{energia(r['gap_mwh_ano'])} (parte do potencial ainda não "
            "aproveitada; gap = potencial − produção). O gap equivale a "
            f"{pct(r['gap_mwh_ano'] / r['x_mwh_ano'] if r['x_mwh_ano'] else None)} "
            "do potencial."
        ),
        f"{r['nome']}: taxa de realização de {pct(r['taxa_realizacao'])}"
        + (
            "."
            if r["nivel"] == "brasil"
            else f" (Brasil: {pct(brasil['taxa_realizacao'])}; "
            + (
                "acima"
                if r["taxa_realizacao"] > brasil["taxa_realizacao"]
                else "abaixo"
            )
            + " da média nacional)."
        ),
        (
            f"{r['nome']}: irradiação média de "
            f"{numero(r['irradiacao_kwh_m2_dia'], 2)} kWh/m²/dia e "
            f"{numero(r['domicilios'])} domicílios."
        ),
    ]
    if r["nivel"] != "municipio":
        fatos.append(f"{r['nome']}: {numero(r['n_municipios'])} municípios.")
    if r["n_municipios_taxa_acima_1"] and r["nivel"] != "municipio":
        fatos.append(
            f"{r['nome']}: {r['n_municipios_taxa_acima_1']} município(s) com taxa "
            "acima de 100% (produção maior que o potencial residencial estimado)."
        )
    return ResultadoFerramenta(
        "resumo_potencial", {"uf": uf, "cod_ibge": cod_ibge}, fatos, r
    )


# Ações por família de fator que REDUZ a taxa (grupo SHAP) e pelo nível do
# fator no recorte, comparado à mediana dos municípios. O nível importa: em
# Caxias do Sul a densidade reduz a taxa por ser ALTA (mais apartamentos, menos
# telhado próprio), enquanto num município pequeno ela reduz por ser baixa.
ACOES_POR_FATOR = {
    ("renda", "baixo"): (
        "Renda abaixo da mediana limita a compra à vista: priorizar financiamento "
        "com parcela menor que a economia na conta, geração compartilhada "
        "(Lei 14.300) e assinatura de energia solar."
    ),
    ("log_densidade_hab_km2", "alto"): (
        "Densidade alta indica mais apartamentos e menos telhado próprio: oferecer "
        "geração compartilhada, autoconsumo remoto e projetos para condomínios."
    ),
    ("log_densidade_hab_km2", "baixo"): (
        "Densidade baixa encarece a venda porta a porta: agrupar a demanda "
        "(compras coletivas, cooperativas, parceria com a prefeitura)."
    ),
    ("log_populacao", "alto"): (
        "Município grande: mercado fragmentado entre prédios e casas; segmentar "
        "por bairro e tipo de imóvel, com condomínios como canal."
    ),
    ("log_populacao", "baixo"): (
        "Mercado pequeno: atender a partir de um polo regional, com equipe "
        "itinerante, em vez de abrir operação local."
    ),
    ("pct_populacao_urbana", "alto"): (
        "Município muito urbano não tem o motor rural da GD: o mercado depende de "
        "casas e condomínios urbanos, com crédito e informação ao consumidor."
    ),
    ("pct_populacao_urbana", "baixo"): (
        "População mais rural: foco nas propriedades, com crédito rural para "
        "energia renovável e sistemas para bombeamento e refrigeração."
    ),
    ("agropecuaria", "baixo"): (
        "Pouca agropecuária: falta a demanda rural que puxa a adoção em outras "
        "regiões; o mercado depende do consumidor urbano e do pequeno comércio."
    ),
    ("agropecuaria", "alto"): (
        "Economia agropecuária: abordar a demanda via cooperativas agrícolas e "
        "linhas de crédito rural, não só pelo consumidor urbano."
    ),
    ("tarifa_b1_rs_mwh", "baixo"): (
        "Tarifa abaixo da mediana alonga o retorno do investimento: comunicar o "
        "payback real e priorizar consumidores de maior consumo."
    ),
    ("icms_meses_isencao", "baixo"): (
        "Isenção de ICMS mais recente que nas outras UFs: o mercado começou depois; "
        "para o investidor, sinal de mercado menos maduro."
    ),
    ("distribuicao", None): (
        "Distribuidora múltipla ou cooperativa de eletrificação: mapear prazos de "
        "parecer de acesso e conexão antes de vender, pois variam por agente."
    ),
    ("irradiacao_kwh_m2_dia", "baixo"): (
        "Irradiação abaixo da mediana reduz a geração por kWp: não é alavanca de "
        "gestão, mas exige dimensionar o sistema com mais módulos."
    ),
}
# Fator que representa cada família na comparação com a mediana.
FATOR_DO_GRUPO = {
    "renda": "renda_domiciliar_pc_media",
    "agropecuaria": "pct_vab_agropecuaria",
}


def _nivel(base: svc.BasePotencial, grupo: str, fatores: list[dict]) -> str | None:
    """'alto' ou 'baixo' em relação à mediana dos municípios (None: booleano)."""
    chave = FATOR_DO_GRUPO.get(grupo, grupo)
    fator = svc.FATORES.get(chave)
    if fator is None or fator.booleano:
        return None
    valor = next((f["valor"] for f in fatores if f["fator"] == chave), None)
    mediana = base.fatores[fator.coluna_valor].astype(float).median()
    if valor is None or pd.isna(mediana):
        return None
    return "alto" if valor > mediana else "baixo"


def explicar_gap(
    ctx: Contexto, uf: str | None = None, cod_ibge: str | None = None
) -> ResultadoFerramenta:
    """Fatores associados à taxa de realização (SHAP) e ações por barreira."""
    e = svc.explicar(ctx.base, ctx.visao, uf=uf, cod_ibge=cod_ibge)
    nome = e["nome"]
    # Sentido escrito: em Mato Grosso o modelo chamou 47,5% de "abaixo do
    # esperado (44,7%)".
    diferenca = e["diferenca_pp"]
    sentido = (
        "; acima do esperado" if diferenca > 0
        else "; abaixo do esperado" if diferenca < 0
        else ""
    )  # fmt: skip
    fatos = [
        (
            f"{nome}: taxa observada de {pct(e['taxa_observada'])}; pelo perfil, o modelo "
            f"esperaria {pct(e['taxa_prevista'])} (diferença de "
            f"{numero(diferenca, 1)} p.p.{sentido})."
        ),
    ]
    # Contribuições abaixo de 0,5 p.p. são ruído para a leitura de gestão.
    relevantes = [g for g in e["grupos"] if abs(g["contribuicao_pp"]) >= 0.5]
    reduzem = [g for g in relevantes if g["efeito"] == "reduz"][:3]
    elevam = [g for g in relevantes if g["efeito"] == "eleva"][:3]
    if reduzem:
        fatos.append(
            f"{nome}, fatores que puxam a taxa para baixo: "
            + "; ".join(
                f"{g['rotulo']} ({numero(g['contribuicao_pp'], 1)} p.p.)"
                for g in reduzem
            )
            + "."
        )
    if elevam:
        fatos.append(
            f"{nome}, fatores que puxam a taxa para cima: "
            + "; ".join(
                f"{g['rotulo']} (+{numero(g['contribuicao_pp'], 1)} p.p.)"
                for g in elevam
            )
            + "."
        )
    if e["nivel"] == "municipio":
        valores = {f["fator"]: f["valor_texto"] for f in e["fatores"]}
        fatos.append(
            f"{nome}, perfil: renda domiciliar per capita média de "
            f"{valores.get('renda_domiciliar_pc_media')}, tarifa B1 de "
            f"{valores.get('tarifa_b1_rs_mwh')}, população urbana de "
            f"{valores.get('pct_populacao_urbana')} e agropecuária com "
            f"{valores.get('pct_vab_agropecuaria')} do VAB."
        )
    acoes = []
    niveis = []
    for g in reduzem:
        if abs(g["contribuicao_pp"]) < 1:
            continue
        nivel = _nivel(ctx.base, g["grupo"], e["fatores"])
        if nivel:
            niveis.append(
                f"{g['rotulo']} {'acima' if nivel == 'alto' else 'abaixo'} da mediana"
            )
        acao = ACOES_POR_FATOR.get((g["grupo"], nivel))
        if acao:
            acoes.append({"fator": g["rotulo"], "nivel": nivel, "acao": acao})
    for acao in acoes:
        acao["recorte"] = nome
    if niveis:
        fatos.append(
            f"{nome}, posição dos fatores que reduzem a taxa em relação à mediana dos "
            f"municípios: {'; '.join(niveis)}."
        )
    if e["diferenca_pp"] <= -svc.TOLERANCIA_ESPERADO_PP:
        acoes.insert(
            0,
            {
                "fator": "Adoção abaixo do perfil",
                "nivel": None,
                "acao": (
                    "A adoção está abaixo do que o perfil comporta: há demanda não "
                    "atendida que os fatores medidos não explicam. Indica falta de "
                    "oferta, informação ou instaladores locais; vale prospecção ativa."
                ),
            },
        )
    for acao in acoes:
        acao["recorte"] = nome
    fatos.append(
        "Leitura do SHAP: associação, não causalidade; descreve como o modelo usa "
        "cada fator, não o efeito de mudá-lo."
    )
    dados = {
        k: e[k]
        for k in ("nome", "taxa_observada", "taxa_prevista", "diferenca_pp", "grupos")
    } | {"acoes": acoes, "aviso_visao": e["aviso_visao"]}
    return ResultadoFerramenta(
        "explicar_gap", {"uf": uf, "cod_ibge": cod_ibge}, fatos, dados
    )


def tabela_oportunidades(
    base: svc.BasePotencial,
    visao: str,
    uf: str | None = None,
    min_domicilios: int = 5000,
) -> pd.DataFrame:
    """Municípios com gap acima do esperado (ver docstring do módulo)."""
    municipal = svc._com_visao(base.municipal, visao)
    tabela = municipal.merge(
        base.shap[["cod_ibge", "previsao", "usado_no_treino"]], on="cod_ibge"
    )
    tabela = tabela[tabela["usado_no_treino"].astype(bool)]
    tabela = tabela[tabela["domicilios"] >= min_domicilios]
    if uf:
        tabela = tabela[tabela["uf"] == uf]
    deficit = (tabela["previsao"] - tabela["taxa_visao"]).clip(lower=0)
    tabela = tabela.assign(
        deficit_pp=deficit * 100,
        gap_acima_esperado_mwh_ano=deficit * tabela["x_mwh_ano"],
    )
    return tabela.sort_values("gap_acima_esperado_mwh_ano", ascending=False)[
        [
            "cod_ibge", "nome", "uf", "domicilios", "x_mwh_ano", "gap_visao",
            "taxa_visao", "previsao", "deficit_pp", "gap_acima_esperado_mwh_ano",
        ]
    ].rename(columns={"gap_visao": "gap_mwh_ano", "taxa_visao": "taxa_realizacao",
                      "previsao": "taxa_prevista"})  # fmt: skip


def oportunidades(
    ctx: Contexto, uf: str | None = None, n: int = 5, cod_ibge: str | None = None
) -> ResultadoFerramenta:
    """Municípios prioritários: maior gap acima do esperado pelo perfil."""
    uf = svc.validar_uf(ctx.base, uf)
    n = max(1, min(int(n or 5), 10))
    tabela = tabela_oportunidades(ctx.base, ctx.visao, uf)
    total = tabela["gap_acima_esperado_mwh_ano"].sum()
    topo = tabela.head(n)
    onde = uf or "Brasil"
    fatos = [
        (
            "Critério do ranking de oportunidades: gap acima do esperado = (taxa "
            "esperada pelo perfil do município − taxa observada) × potencial. Não é o "
            "potencial total nem o gap total: é a adoção que o perfil comportaria e "
            "não aconteceu (associação, não causalidade)."
        ),
        (
            f"{onde}: {numero((tabela['deficit_pp'] > 0).sum())} municípios (com pelo "
            f"menos 5.000 domicílios) estão abaixo da taxa esperada pelo perfil; somam "
            f"{energia(total)} de gap acima do esperado."
        ),
    ]
    for i, linha in enumerate(topo.itertuples(), start=1):
        fatos.append(
            f"{i}º {linha.nome} ({linha.uf}): taxa de {pct(linha.taxa_realizacao)} "
            f"contra {pct(linha.taxa_prevista)} esperada; gap acima do esperado de "
            f"{energia(linha.gap_acima_esperado_mwh_ano)}; "
            f"{numero(linha.domicilios)} domicílios."
        )
    dados = topo.to_dict(orient="records")
    return ResultadoFerramenta("oportunidades", {"uf": uf, "n": n}, fatos, dados)


def comparar_ufs(
    ctx: Contexto, ufs: list[str] | None = None, uf: str | None = None,
    cod_ibge: str | None = None,
) -> ResultadoFerramenta:  # fmt: skip
    """Ranking das UFs pela taxa de realização (ou só as UFs pedidas)."""
    tabela = svc._com_visao(ctx.base.municipal, ctx.visao)
    agregado = tabela.groupby("uf").agg(
        x=("x_mwh_ano", "sum"), y=("y_visao", "sum"), regiao=("regiao", "first")
    )
    agregado["gap"] = agregado["x"] - agregado["y"]
    agregado["taxa"] = agregado["y"] / agregado["x"]
    agregado = agregado.sort_values("taxa", ascending=False)
    agregado["posicao"] = range(1, len(agregado) + 1)
    pedidas = [u.upper() for u in (ufs or []) if u and u.upper() in agregado.index]
    if uf and uf.upper() in agregado.index and uf.upper() not in pedidas:
        pedidas.insert(0, uf.upper())
    fatos = []
    if pedidas:
        for sigla in pedidas:
            l = agregado.loc[sigla]
            fatos.append(
                f"{sigla}: {int(l['posicao'])}º lugar entre as 27 UFs em taxa de "
                f"realização ({pct(l['taxa'])}); gap de {energia(l['gap'])}."
            )
        if len(pedidas) >= 2:
            # Conclusão pronta: o LLM confundia gap absoluto com eficiência.
            ordem = sorted(pedidas[:2], key=lambda u: -agregado.loc[u, "taxa"])
            frente, atras = agregado.loc[ordem[0]], agregado.loc[ordem[1]]
            # diferença dos valores já arredondados, para bater com o que se lê
            diferenca = round(frente["taxa"] * 100, 1) - round(atras["taxa"] * 100, 1)
            fatos.append(
                f"Conclusão da comparação: {ordem[0]} aproveita melhor o potencial que "
                f"{ordem[1]} (taxa de {pct(frente['taxa'])} contra "
                f"{pct(atras['taxa'])}, diferença de {numero(diferenca, 1)} p.p.). "
                "Quem tem taxa maior está à frente; o gap absoluto depende do tamanho "
                "do estado e não mede eficiência."
            )
    else:
        topo, fim = agregado.head(3), agregado.tail(3)
        fatos.append(
            "Maiores taxas de realização: "
            + "; ".join(f"{u} ({pct(r['taxa'])})" for u, r in topo.iterrows())
            + "."
        )
        fatos.append(
            "Menores taxas de realização: "
            + "; ".join(f"{u} ({pct(r['taxa'])})" for u, r in fim.iterrows())
            + "."
        )
        maiores_gaps = agregado.sort_values("gap", ascending=False).head(3)
        fatos.append(
            "Maiores gaps absolutos: "
            + "; ".join(
                f"{u} ({energia(r['gap'])})" for u, r in maiores_gaps.iterrows()
            )
            + "."
        )
    dados = agregado.reset_index().to_dict(orient="records")
    return ResultadoFerramenta("comparar_ufs", {"ufs": pedidas}, fatos, dados)


def cenarios_climaticos(
    ctx: Contexto, uf: str | None = None, cod_ibge: str | None = None
) -> ResultadoFerramenta:
    """Variação da irradiação e do potencial em 2030–2050 (CMIP6, método delta)."""
    if cod_ibge:
        tabela = svc.cenarios_municipio(ctx.base, cod_ibge, ctx.visao)
    else:
        tabela = svc.cenarios_uf(ctx.base, ctx.visao, uf=uf)
        if not uf:  # Brasil: soma das UFs por cenário e janela
            tabela = tabela.groupby(["cenario", "rotulo_cenario", "janela"], as_index=False)[
                ["x_atual_mwh_ano", "x_projetado_mwh_ano", "x_projetado_min_mwh_ano",
                 "x_projetado_max_mwh_ano"]
            ].sum()  # fmt: skip
            tabela["delta_mediano"] = (
                tabela["x_projetado_mwh_ano"] / tabela["x_atual_mwh_ano"] - 1
            )
            tabela["delta_min"] = (
                tabela["x_projetado_min_mwh_ano"] / tabela["x_atual_mwh_ano"] - 1
            )
            tabela["delta_max"] = (
                tabela["x_projetado_max_mwh_ano"] / tabela["x_atual_mwh_ano"] - 1
            )
    nome = _rotulo(uf, cod_ibge, ctx.base)
    fatos = []
    for linha in tabela.itertuples():
        fatos.append(
            f"{nome}, {svc.CENARIOS[linha.cenario]}, {linha.janela}: irradiação "
            f"{pct(linha.delta_mediano, 1)} (faixa entre modelos de "
            f"{pct(linha.delta_min, 1)} a {pct(linha.delta_max, 1)}); potencial "
            f"projetado de {energia(linha.x_projetado_mwh_ano)}."
        )
    maior = tabela["delta_mediano"].abs().max()
    if maior < 0.05:
        fatos.append(
            f"Conclusão dos cenários: até 2050 a irradiação de {nome} varia no máximo "
            f"{pct(maior, 1)} (mediana dos modelos). O clima futuro não explica o gap "
            "de hoje: o gap atual é socioeconômico, não físico."
        )
    else:
        fatos.append(
            f"Conclusão dos cenários: variação de até {pct(maior, 1)} na irradiação de "
            f"{nome}; relevante para dimensionar sistemas, mas não explica o gap de hoje."
        )
    fatos.append(
        "Cenário com faixa de incerteza, não previsão: muda só a irradiação, com a "
        "potência instalada fixa; a taxa de realização não muda."
    )
    colunas = ["cenario", "janela", "delta_mediano", "delta_min", "delta_max",
               "x_atual_mwh_ano", "x_projetado_mwh_ano"]  # fmt: skip
    dados = tabela[colunas].to_dict(orient="records")
    return ResultadoFerramenta(
        "cenarios_climaticos", {"uf": uf, "cod_ibge": cod_ibge}, fatos, dados
    )


def politica_icms(
    ctx: Contexto, uf: str | None = None, cod_ibge: str | None = None
) -> ResultadoFerramenta:
    """Adesão da UF à isenção de ICMS na geração distribuída (CONFAZ)."""
    if ctx.icms is None:
        return ResultadoFerramenta(
            "politica_icms", {"uf": uf}, [], erro="Dados do ICMS ausentes."
        )
    if not uf:
        tabela = ctx.icms.sort_values("inicio_efeitos")
        primeiras = ", ".join(tabela["sigla_uf"].head(6))
        ultimas = ", ".join(tabela["sigla_uf"].tail(3))
        fatos = [
            (
                f"As {len(tabela)} UFs aderiram à isenção de ICMS na GD (Convênio ICMS "
                f"16/15 e adesões). Primeiras, com efeitos em 09/2015: {primeiras}. "
                f"Últimas, em 07/2018: {ultimas}."
            )
        ]
        return ResultadoFerramenta("politica_icms", {"uf": None}, fatos, {})
    linha = ctx.icms[ctx.icms["sigla_uf"] == uf.upper()]
    if linha.empty:
        return ResultadoFerramenta(
            "politica_icms", {"uf": uf}, [f"{uf}: sem registro de adesão no CONFAZ."]
        )
    l = linha.iloc[0]
    inicio = pd.Timestamp(l["inicio_efeitos"]).strftime("%m/%Y")
    fatos = [
        (
            f"{uf}: isenção de ICMS na GD pelo Convênio {l['convenio_adesao']}, com "
            f"efeitos desde {inicio} ({numero(l['meses_desde_inicio'])} meses)."
        ),
    ]
    return ResultadoFerramenta(
        "politica_icms", {"uf": uf}, fatos,
        {"convenio": l["convenio_adesao"], "inicio_efeitos": inicio,
         "meses": int(l["meses_desde_inicio"])},
    )  # fmt: skip


def adocao_uf(
    ctx: Contexto, uf: str | None = None, cod_ibge: str | None = None
) -> ResultadoFerramenta:
    """Watts por habitante e posição da UF (indicadores do TP1–TP3)."""
    if ctx.agregado is None or ctx.dim_uf is None or not uf:
        return ResultadoFerramenta("adocao_uf", {"uf": uf}, [], erro="Informe uma UF.")
    inicio, fim = indicadores.anos_disponiveis(ctx.agregado)
    classes = tuple(indicadores.classes_disponiveis(ctx.agregado))
    tabela = indicadores.indicadores_por_uf(
        ctx.agregado, ctx.dim_uf, inicio, fim, classes, ctx.visao
    )
    pos = indicadores.posicoes(tabela, uf.upper())
    linha = tabela[tabela["sigla_uf"] == uf.upper()].iloc[0]
    media = indicadores.media_brasil(tabela)
    fatos = [
        (
            f"{uf}: {numero(linha['watts_por_habitante'], 1)} W por habitante em GD solar "
            f"(todas as classes, {inicio}–{fim}), {pos['watts_por_habitante']}º lugar; "
            f"média do Brasil de {numero(media['watts_por_habitante'], 1)} W/hab."
        ),
        (
            f"{uf}: {numero(linha['potencia_mw'], 1)} MW instalados em "
            f"{numero(linha['qtd_empreendimentos'])} empreendimentos."
        ),
    ]
    return ResultadoFerramenta(
        "adocao_uf", {"uf": uf}, fatos,
        {"watts_por_habitante": float(linha["watts_por_habitante"]),
         "posicao": pos["watts_por_habitante"]},
    )  # fmt: skip


def noticias(
    ctx: Contexto, termo: str | None = None, uf: str | None = None, n: int = 3,
    cod_ibge: str | None = None,
) -> ResultadoFerramenta:  # fmt: skip
    """Notícias mais recentes do corpus julgadas relevantes (TP2–TP4)."""
    if ctx.corpus is None or ctx.corpus.empty:
        return ResultadoFerramenta(
            "noticias", {"termo": termo}, [], erro="Corpus ausente."
        )
    n = max(1, min(int(n or 3), 5))
    relevantes = filtrar_noticias(ctx.corpus, relevante=True)
    selecao = filtrar_noticias(relevantes, termo=termo or None, uf=uf)
    if selecao.empty and uf:
        selecao = filtrar_noticias(relevantes, termo=termo or None)
    if selecao.empty:
        selecao = relevantes
    selecao = selecao.sort_values("data_publicacao", ascending=False).head(n)
    fatos, dados = [], []
    for linha in selecao.itertuples():
        data = pd.Timestamp(linha.data_publicacao).strftime("%d/%m/%Y")
        resumo = linha.resumo if isinstance(linha.resumo, str) and linha.resumo else ""
        fatos.append(
            f"Notícia de {data} ({linha.fonte}): {linha.titulo}."
            + (f" Resumo automático: {resumo}" if resumo else "")
        )
        dados.append({"data": data, "fonte": linha.fonte, "titulo": linha.titulo,
                      "url": linha.url})  # fmt: skip
    return ResultadoFerramenta(
        "noticias", {"termo": termo, "uf": uf, "n": n}, fatos, dados
    )


CATALOGO: dict[str, Ferramenta] = {
    f.nome: f
    for f in [
        Ferramenta("resumo_potencial", "Potencial, produção, gap e taxa de realização do recorte.",
                   resumo_potencial, "uf?, cod_ibge?"),
        Ferramenta("explicar_gap", "Fatores (SHAP) que explicam a taxa e ações por barreira.",
                   explicar_gap, "uf?, cod_ibge?"),
        Ferramenta("oportunidades", "Municípios prioritários para investir (gap acima do esperado).",
                   oportunidades, "uf?, n?"),
        Ferramenta("comparar_ufs", "Ranking ou comparação de UFs pela taxa de realização.",
                   comparar_ufs, "ufs? (lista de siglas)"),
        Ferramenta("cenarios_climaticos", "Irradiação e potencial projetados para 2030–2050.",
                   cenarios_climaticos, "uf?, cod_ibge?"),
        Ferramenta("politica_icms", "Isenção de ICMS na geração distribuída da UF.",
                   politica_icms, "uf?"),
        Ferramenta("adocao_uf", "Watts por habitante e posição da UF no ranking de adoção.",
                   adocao_uf, "uf"),
        Ferramenta("noticias", "Notícias recentes e relevantes sobre GD solar e regulação.",
                   noticias, "termo?, uf?, n?"),
    ]
}  # fmt: skip


def executar(ctx: Contexto, nome: str, argumentos: dict) -> ResultadoFerramenta:
    """Executa uma ferramenta do catálogo, descartando argumentos que ela não
    aceita (o LLM às vezes inventa) e transformando falhas em erro legível."""
    ferramenta = CATALOGO.get(nome)
    if ferramenta is None:
        return ResultadoFerramenta(
            nome, argumentos, [], erro="Ferramenta desconhecida."
        )
    aceitos = set(inspect.signature(ferramenta.funcao).parameters) - {"ctx"}
    limpos = {
        k: v
        for k, v in (argumentos or {}).items()
        if k in aceitos and v not in ("", None)
    }
    try:
        return ferramenta.funcao(ctx, **limpos)
    except svc.RecorteInexistente as erro:
        return ResultadoFerramenta(nome, limpos, [], erro=str(erro))
    except (KeyError, ValueError, TypeError, IndexError) as erro:
        return ResultadoFerramenta(nome, limpos, [], erro=f"Falha na consulta: {erro}")
