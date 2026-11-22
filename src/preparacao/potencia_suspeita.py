"""
PROJETO: SolarGap Brasil
ARQUIVO: potencia_suspeita.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 20/11/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Tratamento da potência suspeita na camada Silver: registros com potência de
    exatamente 75 kW (teto da microgeração) usada como valor de preenchimento
    por uma distribuidora. Mesmo padrão da fonte imputada do Maranhão:
    nenhum registro é excluído, o dado oficial é preservado e a correção fica
    em colunas próprias, para que o painel ofereça as duas visões.

ACHADO (base ANEEL 10/2026):
    47 mil registros solares da COPEL-DIS com exatamente 75 kW, inclusive 28 mil
    residências, cuja mediana é de 5 kW. A base reproduz o painel oficial, então
    a inconsistência está na fonte (docs/potencial/atualizacao_base_10_2026.md).

1. DIAGNÓSTICO POR DISTRIBUIDORA (nenhuma UF ou distribuidora fixada no código):
    - fração de registros com exatamente 75 kW na classe Residencial, onde o
      valor é fisicamente implausível;
    - limite robusto entre distribuidoras: mediana + 5 x MAD das frações;
    - sinalizada se o limite inferior do intervalo de Wilson (95%) da sua fração
      ficar acima do limite.
    Por que a classe Residencial e o intervalo de Wilson: a regra aplicada à
    fração de TODAS as classes sinalizava 14 distribuidoras, quase todas
    cooperativas rurais, onde 75 kW é porte legítimo de propriedades rurais e
    comércios. Restrita à classe Residencial, mas sem o Wilson, sinalizava
    cooperativas com 2 a 13 registros: com amostras tão pequenas, a fração é
    ruído. Com as duas condições, só a COPEL-DIS é sinalizada (12,2% contra um
    limite de 0,85%; a segunda maior, COPREL, tem limite inferior de 0,82%).

2. SINALIZAÇÃO:
    flag_potencia_suspeita = True em TODOS os registros com exatamente 75 kW das
    distribuidoras sinalizadas, em qualquer classe. Nenhum registro é excluído.

3. IMPUTAÇÃO (potencia_corrigida_kw):
    Mediana da potência dos registros NÃO sinalizados, no primeiro nível com ao
    menos MIN_AMOSTRA_IMPUTACAO registros:
        municipio_classe_ano     município + classe + ano de conexão
        municipio_classe         município + classe
        distribuidora_classe_ano distribuidora + classe + ano
        uf_classe                UF + classe
    O nível usado fica em nivel_imputacao_potencia. Registro sinalizado sem
    nenhum nível disponível mantém a potência original (nivel "sem_imputacao").
    Registros não sinalizados: potencia_corrigida_kw = potencia_kw.

SENSIBILIDADE (limite conservador):
    potencia_conservadora_kw: imputa só os sinalizados da classe Residencial e
    mantém os 75 kW das demais classes (comerciais, rurais e industriais podem,
    de fato, ter 75 kW).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.preparacao import esquema

CLASSE_AUSENTE = "Não informada"

NIVEIS_IMPUTACAO: list[tuple[str, list[str]]] = [
    ("municipio_classe_ano", ["cod_municipio", "classe_consumo", "ano"]),
    ("municipio_classe", ["cod_municipio", "classe_consumo"]),
    ("distribuidora_classe_ano", ["distribuidora", "classe_consumo", "ano"]),
    ("uf_classe", ["sigla_uf", "classe_consumo"]),
]
SEM_IMPUTACAO = "sem_imputacao"


# ═══════════════════ 1. Diagnóstico ═══════════════════


def limite_inferior_wilson(k, n, z: float = esquema.Z_WILSON):
    """Limite inferior do intervalo de Wilson para a proporção k/n.

    Adequado a proporções pequenas e amostras pequenas, em que o intervalo
    normal (p ± z·√(p(1−p)/n)) sai do intervalo [0, 1] e superestima a certeza.
    """
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = k / n
        denominador = 1 + z**2 / n
        centro = p + z**2 / (2 * n)
        margem = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
        limite = (centro - margem) / denominador
    return np.where(n > 0, limite, np.nan)


def diagnosticar_distribuidoras(
    registros: pd.DataFrame,
    valor_kw: float = esquema.POTENCIA_SUSPEITA_KW,
    classe: str = esquema.CLASSE_DIAGNOSTICO_POTENCIA,
    fator_mad: float = esquema.FATOR_MAD,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Fração de registros com exatamente valor_kw por distribuidora.

    Entrada: distribuidora, classe_consumo, potencia_kw (um registro por
    empreendimento). Devolve (tabela por distribuidora, referências usadas).
    """
    exato = registros["potencia_kw"] == valor_kw
    na_classe = registros["classe_consumo"] == classe

    tabela = (
        pd.DataFrame(
            {
                "distribuidora": registros["distribuidora"],
                "n_total": 1,
                "n_valor_total": exato.astype(int),
                "n_classe": na_classe.astype(int),
                "n_valor_classe": (exato & na_classe).astype(int),
            }
        )
        .groupby("distribuidora", dropna=False)
        .sum()
    )
    # Só distribuidoras com registros na classe entram no cálculo do limite.
    tabela = tabela[tabela["n_classe"] > 0].copy()
    tabela["fracao_classe"] = tabela["n_valor_classe"] / tabela["n_classe"]
    tabela["wilson_inferior"] = limite_inferior_wilson(
        tabela["n_valor_classe"], tabela["n_classe"]
    )

    mediana = float(tabela["fracao_classe"].median())
    mad = float((tabela["fracao_classe"] - mediana).abs().median())
    limite = mediana + fator_mad * mad
    tabela["sinalizada"] = tabela["wilson_inferior"] > limite

    referencias = {"mediana": mediana, "mad": mad, "limite": limite}
    return (
        tabela.sort_values("fracao_classe", ascending=False).reset_index(),
        referencias,
    )


# ═══════════════════ 2. Sinalização ═══════════════════


def sinalizar(
    registros: pd.DataFrame,
    distribuidoras: list[str] | set[str],
    valor_kw: float = esquema.POTENCIA_SUSPEITA_KW,
) -> pd.Series:
    """True nos registros com exatamente valor_kw das distribuidoras sinalizadas."""
    return (registros["potencia_kw"] == valor_kw) & registros["distribuidora"].isin(
        list(distribuidoras)
    )


# ═══════════════════ 3. Imputação ═══════════════════


def imputar_potencia(
    registros: pd.DataFrame,
    sinalizados: pd.Series,
    minimo: int = esquema.MIN_AMOSTRA_IMPUTACAO,
) -> tuple[pd.Series, pd.Series]:
    """Potência corrigida e nível de imputação de cada registro.

    Devolve (potencia_corrigida_kw, nivel_imputacao_potencia). O nível é nulo
    nos registros não sinalizados.
    """
    df = registros.assign(
        classe_consumo=registros["classe_consumo"].fillna(CLASSE_AUSENTE)
    )
    corrigida = df["potencia_kw"].astype("float64").copy()
    nivel = pd.Series(pd.NA, index=df.index, dtype="string")
    pendentes = sinalizados.fillna(False).astype(bool).copy()
    referencia = df[~pendentes]

    for nome, chaves in NIVEIS_IMPUTACAO:
        if not pendentes.any():
            break
        medianas = (
            referencia.groupby(chaves, dropna=False)["potencia_kw"]
            .agg(mediana="median", n="size")
            .query("n >= @minimo")["mediana"]
        )
        alvo = df.loc[pendentes, chaves]
        encontrados = alvo.join(medianas, on=chaves)["mediana"].dropna()
        corrigida.loc[encontrados.index] = encontrados.to_numpy()
        nivel.loc[encontrados.index] = nome
        pendentes.loc[encontrados.index] = False

    nivel.loc[pendentes] = SEM_IMPUTACAO
    return corrigida, nivel


# ═══════════════════ Aplicação na Silver ═══════════════════


def aplicar_tratamento(silver: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Acrescenta as colunas do tratamento à Silver inteira.

    Colunas novas: flag_potencia_suspeita, potencia_corrigida_kw,
    nivel_imputacao_potencia, potencia_conservadora_kw.
    Devolve (Silver tratada, diagnóstico por distribuidora).
    """
    diagnostico, referencias = diagnosticar_distribuidoras(silver)
    sinalizadas = diagnostico.loc[diagnostico["sinalizada"], "distribuidora"].tolist()
    logging.info(
        "Potência suspeita (%.0f kW, classe %s): mediana %.4f%%, MAD %.4f%%, "
        "limite %.4f%% -> distribuidoras sinalizadas: %s",
        esquema.POTENCIA_SUSPEITA_KW,
        esquema.CLASSE_DIAGNOSTICO_POTENCIA,
        100 * referencias["mediana"],
        100 * referencias["mad"],
        100 * referencias["limite"],
        sinalizadas or "nenhuma",
    )

    flag = sinalizar(silver, sinalizadas)
    corrigida, nivel = imputar_potencia(silver, flag)

    tratada = silver.copy()
    tratada["flag_potencia_suspeita"] = flag.astype(bool)
    tratada["potencia_corrigida_kw"] = corrigida
    tratada["nivel_imputacao_potencia"] = nivel
    residencial = tratada["classe_consumo"] == esquema.CLASSE_DIAGNOSTICO_POTENCIA
    tratada["potencia_conservadora_kw"] = tratada["potencia_kw"].where(
        ~(tratada["flag_potencia_suspeita"] & residencial),
        tratada["potencia_corrigida_kw"],
    )

    logging.info(
        "Registros sinalizados: %d | %.1f kW -> %.1f kW (corrigida) | níveis: %s",
        int(flag.sum()),
        tratada.loc[flag, "potencia_kw"].sum(),
        tratada.loc[flag, "potencia_corrigida_kw"].sum(),
        nivel.value_counts().to_dict(),
    )
    return tratada, diagnostico
