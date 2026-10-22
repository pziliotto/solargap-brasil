"""Serviço de upload (TP2): formatos aceitos e mensagens de erro."""

from src.app.validacao_upload import gerar_modelo, validar_upload


def test_modelo_tem_27_ufs():
    linhas = gerar_modelo().decode("utf-8-sig").strip().splitlines()
    assert linhas[0] == "sigla_uf;nome_uf;valor" and len(linhas) == 28


def test_aceita_decimal_brasileiro_e_virgula_como_separador():
    resultado = validar_upload(b"sigla_uf;clientes\nRS;1.234,5\nsc;10\n")
    assert not resultado.erros and resultado.coluna_valor == "clientes"
    assert resultado.dados.set_index("sigla_uf").loc["RS", "clientes"] == 1234.5
    resultado = validar_upload(b"sigla_uf,metas\nRS,10.5\nSP,3\n")
    assert not resultado.erros and resultado.dados["metas"].tolist() == [10.5, 3.0]


def test_erros_especificos():
    assert any("obrigatória" in e for e in validar_upload(b"uf;valor\nRS;1\n").erros)
    assert any(
        "inválidas" in e for e in validar_upload(b"sigla_uf;valor\nXX;1\n").erros
    )
    assert any(
        "repetidas" in e for e in validar_upload(b"sigla_uf;valor\nRS;1\nRS;2\n").erros
    )
    assert any(
        "não numéricos" in e for e in validar_upload(b"sigla_uf;valor\nRS;abc\n").erros
    )
