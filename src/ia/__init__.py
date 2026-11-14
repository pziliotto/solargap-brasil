"""
PROJETO: SolarGap Brasil
PACOTE: src.ia
AUTORA: Pâmela Lima Ziliotto
CRIAÇÃO: 13/11/2026

DESCRIÇÃO:
    Modelos de linguagem locais (TP4), executados com Transformers/PyTorch na
    própria máquina, sem serviço externo. Três tarefas sobre o corpus de notícias:
        resumo      sumarização abstrativa (família T5)
        tom         favorável / desfavorável / neutro em relação à energia solar
        relevancia  se a notícia trata de fato de energia solar

ESTRUTURA:
    catalogo.py     candidatos avaliados, modelo padrão de cada tarefa e hipóteses
    modelos_hf.py   carga e inferência com Transformers (único módulo que importa torch)
    motor.py        gerenciador: carga única, estados, fila de inferência e erros
    metricas.py     ROUGE com suporte a acentos, acurácia e F1 macro
    benchmark.py    comparação dos candidatos (qualidade, tempo, memória)
    rotulagem.py    gera a planilha de rótulos manuais usada no benchmark

ISOLAMENTO DO TORCH:
    Só modelos_hf.py importa torch/transformers, e só dentro das funções. Assim a
    API, o painel e os testes continuam abrindo rápido — e funcionam (com as rotas
    de IA respondendo 503) numa máquina em que o PyTorch não está instalado.
"""
