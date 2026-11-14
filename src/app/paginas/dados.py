"""
PROJETO: SolarGap Brasil
ARQUIVO: paginas/dados.py
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026 (origem: aba Dados do demo_app.py, TP2)
ATUALIZAÇÃO:

DESCRIÇÃO:
    Serviço de download e upload de arquivos:
        - download dos recortes filtrados (indicadores, série, crescimento,
          ICMS e corpus de notícias);
        - upload de um indicador próprio por UF (CSV) para comparação com a
          adoção de energia solar — validado uma única vez e guardado em
          st.session_state até ser removido.

PRIVACIDADE:
    O arquivo enviado fica só na sessão do navegador: não é gravado em disco
    nem versionado (Data Summary Report, seção 4).
"""

import plotly.express as px
import streamlit as st

from src.app import carregamento as dados
from src.app.componentes import filtros_atuais, para_csv, rodape
from src.app.validacao_upload import gerar_modelo, validar_upload
from src.servicos import indicadores

filtros = filtros_atuais()
metrica = filtros.info_metrica
coluna = filtros.metrica
agregado = dados.carregar_agregado()
indicadores_uf = dados.indicadores_por_uf(
    agregado,
    dados.carregar_uf(),
    filtros.ano_inicio,
    filtros.ano_fim,
    filtros.classes,
    filtros.incluir_imputados,
)

st.session_state.setdefault("upload", None)

st.title("📁 Dados")

# ═══════════════════ Download ═══════════════════

st.subheader("Download")
st.markdown("Os arquivos respeitam os filtros aplicados na barra lateral.")

crescimento, _ = dados.taxa_crescimento(
    agregado,
    filtros.classes,
    filtros.incluir_imputados,
    indicadores.ANO_BASE_CRESCIMENTO,
    indicadores.ANO_FINAL_CRESCIMENTO,
)
icms = dados.carregar_icms()

arquivos = [
    (
        "Indicadores por UF",
        indicadores_uf.drop(columns=["potencia_kw"]),
        "solargap_indicadores_uf.csv",
    ),
    (
        "Série anual por UF",
        dados.serie_anual(
            agregado,
            filtros.ano_inicio,
            filtros.ano_fim,
            filtros.classes,
            filtros.incluir_imputados,
        ),
        "solargap_serie_anual.csv",
    ),
    ("Crescimento 2022-2025", crescimento, "solargap_crescimento.csv"),
    ("Corpus de notícias", dados.carregar_corpus(), "solargap_noticias.csv"),
]
if icms is not None:
    arquivos.append(("Adesão ao ICMS 16/15", icms, "solargap_icms.csv"))

for coluna_botao, (rotulo, tabela, nome) in zip(
    st.columns(len(arquivos)), arquivos, strict=True
):
    coluna_botao.download_button(
        rotulo, para_csv(tabela), file_name=nome, mime="text/csv", width="stretch"
    )

# ═══════════════════ Upload ═══════════════════

st.divider()
st.subheader("Compare com um indicador seu")
st.markdown(
    "Envie um CSV com um valor por UF — carteira de clientes, instaladores, metas — "
    "para compará-lo com a adoção de energia solar. Baixe o modelo, preencha a coluna "
    "`valor` (pode renomeá-la) e envie o arquivo."
)
st.download_button(
    "Baixar modelo (CSV)",
    gerar_modelo(),
    file_name="modelo_solargap.csv",
    mime="text/csv",
)
arquivo = st.file_uploader("Enviar CSV", type=["csv"], key="arquivo_usuario")

# Valida só quando chega um arquivo novo; o resultado fica na sessão.
if arquivo is not None:
    atual = st.session_state["upload"]
    if atual is None or atual["file_id"] != arquivo.file_id:
        st.session_state["upload"] = {
            "file_id": arquivo.file_id,
            "nome": arquivo.name,
            "resultado": validar_upload(arquivo.getvalue()),
        }

enviado = st.session_state["upload"]
if enviado is not None:
    resultado = enviado["resultado"]
    st.markdown(f"Arquivo na sessão: **{enviado['nome']}**")
    for erro in resultado.erros:
        st.error(erro)
    for aviso in resultado.avisos:
        st.warning(aviso)

    if resultado.dados is not None:
        valor = resultado.coluna_valor
        cruzado = indicadores_uf.merge(resultado.dados, on="sigla_uf", how="inner")
        rho = indicadores.correlacao_spearman(cruzado[valor], cruzado[coluna])

        figura = px.scatter(
            cruzado,
            x=valor,
            y=coluna,
            text="sigla_uf",
            color="regiao",
            labels={valor: valor, coluna: metrica.rotulo, "regiao": "Região"},
        )
        figura.update_traces(textposition="top center")
        figura.update_layout(height=480, margin=dict(t=20, b=10))
        st.plotly_chart(figura, width="stretch")
        st.caption(
            f"Correlação de Spearman: {'—' if rho is None else f'{rho:.2f}'.replace('.', ',')}. "
            f"UFs com {metrica.rotulo_frase} alta e {valor} baixo são candidatas a mercado "
            "ainda pouco explorado. A mesma comparação está disponível na API (POST /comparacoes)."
        )
        tabela = cruzado[["sigla_uf", "nome_uf", valor, coluna]].sort_values(
            coluna, ascending=False
        )
        st.dataframe(tabela, hide_index=True, width="stretch")
        st.download_button(
            "Baixar comparação",
            para_csv(tabela),
            file_name="solargap_comparacao.csv",
            mime="text/csv",
        )

    if st.button("Remover arquivo da sessão"):
        st.session_state["upload"] = None
        st.rerun()

rodape()
