"""
PROJETO: SolarGap Brasil
ARQUIVO: validacao_upload.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/09/2026
ATUALIZAÇÃO:

DESCRIÇÃO:
    Serviço de upload do dashboard: gera o CSV-modelo e valida o arquivo
    enviado pelo usuário antes de cruzá-lo com os indicadores.

CASO DE USO:
    O usuário envia um indicador próprio por UF (carteira de clientes,
    número de instaladores, metas) e o compara com a adoção de energia solar
    — por exemplo, para ver onde tem pouca presença justamente onde há
    lacuna de adoção.

FORMATO ACEITO:
    - coluna obrigatória: sigla_uf;
    - uma coluna numérica de valor, com qualquer nome (o nome vira rótulo);
    - separador ";" ou "," detectado automaticamente;
    - decimal com vírgula (1.234,5) ou ponto (1234.5);
    - UFs podem ficar de fora (gera aviso, não erro).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd

from src.preparacao import esquema

COLUNA_UF = "sigla_uf"
COLUNAS_IGNORADAS = {COLUNA_UF, "nome_uf"}


@dataclass
class ResultadoValidacao:
    dados: pd.DataFrame | None = None
    coluna_valor: str | None = None
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def gerar_modelo() -> bytes:
    """CSV com as 27 UFs e a coluna de valor vazia, pronto para preencher."""
    modelo = pd.DataFrame(
        [
            {"sigla_uf": sigla, "nome_uf": nome, "valor": ""}
            for sigla, (_, nome) in esquema.UFS.items()
        ]
    ).sort_values("sigla_uf")
    # utf-8-sig: o Excel no Windows reconhece a acentuação
    return modelo.to_csv(index=False, sep=";").encode("utf-8-sig")


def _ler_csv(conteudo: bytes) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(
                io.BytesIO(conteudo),
                sep=None,
                engine="python",
                dtype=str,
                encoding=encoding,
            )
        except UnicodeDecodeError:
            continue
    raise ValueError("Codificação do arquivo não reconhecida.")


def _converter_numeros(texto: pd.Series) -> pd.Series:
    """Aceita 1.234,5 (padrão brasileiro) e 1234.5 (padrão internacional)."""
    texto = texto.fillna("").str.strip()
    padrao_br = texto.str.contains(",", regex=False)
    texto = texto.where(
        ~padrao_br,
        texto.str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
    )
    return pd.to_numeric(texto.replace("", pd.NA), errors="coerce")


def validar_upload(conteudo: bytes) -> ResultadoValidacao:
    resultado = ResultadoValidacao()

    try:
        df = _ler_csv(conteudo)
    except Exception as erro:  # noqa: BLE001 — qualquer falha de leitura vira mensagem
        resultado.erros.append(f"Não foi possível ler o arquivo como CSV: {erro}")
        return resultado

    df.columns = [c.strip() for c in df.columns]
    colunas_normalizadas = {c.lower(): c for c in df.columns}

    if COLUNA_UF not in colunas_normalizadas:
        resultado.erros.append(
            f"Coluna obrigatória '{COLUNA_UF}' não encontrada. Colunas recebidas: {list(df.columns)}"
        )
        return resultado

    coluna_uf = colunas_normalizadas[COLUNA_UF]
    candidatas = [c for c in df.columns if c.lower() not in COLUNAS_IGNORADAS]
    if not candidatas:
        resultado.erros.append(
            "Nenhuma coluna de valor encontrada além de sigla_uf e nome_uf."
        )
        return resultado
    if len(candidatas) > 1:
        resultado.avisos.append(
            f"Mais de uma coluna de valor; usando a primeira: '{candidatas[0]}'."
        )
    coluna_valor = candidatas[0]

    df[coluna_uf] = df[coluna_uf].fillna("").str.strip().str.upper()
    valores_texto = df[coluna_valor].fillna("").str.strip()

    # Linhas totalmente vazias são ignoradas
    df = df[(df[coluna_uf] != "") | (valores_texto != "")]
    valores_texto = valores_texto.loc[df.index]

    invalidas = sorted(set(df[coluna_uf]) - set(esquema.UFS))
    if invalidas:
        resultado.erros.append(f"Siglas de UF inválidas: {invalidas}")

    duplicadas = sorted(df.loc[df[coluna_uf].duplicated(), coluna_uf].unique())
    if duplicadas:
        resultado.erros.append(f"UFs repetidas no arquivo: {duplicadas}")

    valores = _converter_numeros(valores_texto)
    nao_numericos = (valores_texto != "") & valores.isna()
    if nao_numericos.any():
        ufs_problema = df.loc[nao_numericos, coluna_uf].tolist()
        resultado.erros.append(f"Valores não numéricos nas UFs: {ufs_problema}")

    if valores.notna().sum() == 0:
        resultado.erros.append(
            f"A coluna '{coluna_valor}' não tem nenhum valor preenchido."
        )

    if resultado.erros:
        return resultado

    faltantes = esquema.TOTAL_UFS - int(valores.notna().sum())
    if faltantes:
        resultado.avisos.append(
            f"{faltantes} UF(s) sem valor — ficam de fora da comparação."
        )

    resultado.dados = (
        pd.DataFrame({"sigla_uf": df[coluna_uf], coluna_valor: valores})
        .dropna()
        .reset_index(drop=True)
    )
    resultado.coluna_valor = coluna_valor
    return resultado
