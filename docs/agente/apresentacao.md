# Apresentação da solução final — SolarGap Brasil (TP5)

Roteiro de 8 a 10 minutos, com demonstração ao vivo no painel.

## 1. O problema (1 min)

O Brasil tem um dos melhores recursos solares do mundo, mas a energia solar distribuída se espalhou de forma desigual. Os telhados residenciais do país poderiam gerar **302,6 TWh/ano**; a micro e minigeração residencial e rural produz cerca de **31,5 TWh/ano**, ou **10,4% do potencial**. A taxa varia de 47,5% em Mato Grosso a 4,4% em Sergipe.

Para quem decide (gestor público, investidor, integrador), a pergunta não é "quanto sol tem", mas **onde está a adoção que falta e o que a trava**. **ODS 7** (energia limpa e acessível, metas 7.2 e 7.b) e **ODS 10** (redução das desigualdades).

## 2. O ciclo de ciência de dados (2 min)

| Etapa | O que foi feito | Por que importa |
|---|---|---|
| Coleta | APIs (ANEEL, IBGE, NASA POWER, CMIP6) e web scraping (EBC, gov.br, CONFAZ) | dado oficial e aberto, com licença documentada |
| Preparação | camadas Bronze, Silver e Gold; anomalia dos 75 kW do PR detectada e tratada em três visões | o número do painel é auditável e bate com o painel da ANEEL |
| Modelagem | potencial técnico por município; LightGBM com validação agrupada por UF; SHAP | separa o que o perfil explica do que é atraso de mercado |
| IA (TP4) | PTT5 (resumo) e mDeBERTa (relevância) escolhidos por benchmark | notícias já filtradas e resumidas |
| IA (TP5) | **agente de decisão** com LLM local | transforma todas as etapas anteriores numa resposta |

Mensagem: cada etapa existe porque a seguinte depende dela. O agente não sabe nada sozinho; ele consulta o que o pipeline produziu.

## 3. Demonstração do agente (4 min)

Na página **Agente de decisão**:

1. **"Onde investir em geração distribuída no Rio Grande do Sul?"** O agente devolve os municípios com maior *gap acima do esperado* (Bagé, Viamão, Caxias do Sul), com gráfico. Explicar o indicador: a adoção que o próprio perfil comportaria e não aconteceu.
2. **"Por que Caxias do Sul está abaixo do esperado e o que fazer?"** Diagnóstico (9,0% contra 10,8% esperados), fatores (densidade alta reduz, renda eleva) e recomendações ligadas a cada barreira (geração compartilhada e condomínios).
3. **"E os cenários climáticos?"** (seguimento) A memória mantém Caxias do Sul. A irradiação muda cerca de 1% até 2050: **o gap é socioeconômico, não físico**.
4. Abrir **Evidências**: as ferramentas usadas, os fatos de cada uma e o selo "números conferidos com os dados".
5. Desligar *Usar modelo de linguagem*: o mesmo diagnóstico no modo por regras. A demonstração não depende do modelo estar no ar.

## 4. Por que confiar na resposta (1 min)

- O LLM **não localiza** o município (busca determinística na Gold), **não faz contas** (copia fatos prontos) e **não inventa a recomendação** (escolhe num catálogo de ações por barreira).
- Todo número da resposta é **conferido automaticamente** com os dados consultados; se algum não estiver, o usuário vê o aviso.
- 472 testes automatizados, 61 só do agente, inclusive com um LLM simulado que erra de propósito.

## 5. Limites e próximos passos (1 min)

- Associação, não causalidade: o SHAP mostra a que o gap está associado, não o efeito de uma política.
- Potencial residencial com premissas fixas de telhado; comércio e usinas ficam fora.
- Próximo passo: validar o catálogo de ações com integradores solares e acompanhar a taxa de realização a cada nova base da ANEEL.

## Perguntas prováveis

- **Por que um LLM local e não o ChatGPT?** Coerência com o TP4, custo zero por pergunta e nenhum dado saindo da máquina. O agente aceita uma API online trocando três variáveis de ambiente.
- **E se o modelo inventar um número?** A verificação acusa, e o painel mostra qual número não veio dos dados.
- **Por que Recife lidera as oportunidades do Brasil?** Perfil (renda, irradiação) sugere 6,3% de taxa; a observada é 2,9%. Sobre um potencial grande, isso dá o maior gap acima do esperado do país. A densidade alta (apartamentos) é a principal barreira associada.
