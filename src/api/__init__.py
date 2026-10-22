"""
PROJETO: SolarGap Brasil
PACOTE: src.api
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 21/10/2026

DESCRIÇÃO:
    API REST do projeto (FastAPI), TP3. Expõe a camada Gold por meio da camada
    de serviços (src/servicos) — os mesmos cálculos do dashboard.

ESTRUTURA:
    main.py          aplicação, metadados da documentação e tratamento de erros
    modelos.py       modelos Pydantic de entrada e de resposta (contratos)
    dependencias.py  repositório de dados (carga única) e filtros comuns
    rotas/           um módulo por assunto: sistema, indicadores, notícias,
                     políticas e comparações

EXECUÇÃO (a partir da raiz):
    uvicorn src.api.main:app --reload
    Documentação interativa: http://127.0.0.1:8000/docs
"""
