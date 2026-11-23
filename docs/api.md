# API — SolarGap Brasil

**Versão:** 1.2.0 (TP4.5) · **Tecnologia:** FastAPI + Pydantic · **Código:** `src/api/`

A API expõe a camada Gold do projeto (ANEEL + IBGE), o potencial solar municipal (TP4.5), o corpus de notícias e a adesão ao Convênio ICMS 16/15. Os cálculos vêm de `src/servicos/` — os mesmos usados pelo dashboard, portanto os números são idênticos nos dois canais.

## Como executar

```bash
uvicorn src.api.main:app --reload
```

- Documentação interativa (Swagger): http://127.0.0.1:8000/docs — permite testar cada rota no navegador
- Documentação alternativa (ReDoc): http://127.0.0.1:8000/redoc
- Esquema OpenAPI: http://127.0.0.1:8000/openapi.json

Os dados são lidos **uma vez**, no startup. Se faltar um arquivo obrigatório da Gold, a API sobe mesmo assim e responde **503** com a instrução de correção.

No mesmo startup, os **modelos de linguagem** começam a carregar em segundo plano (TP4). A API fica disponível na hora; enquanto os modelos carregam, só as rotas de IA respondem **503**, com o cabeçalho `Retry-After`. Na primeira execução, os modelos (~2 GB) são baixados para o cache do HuggingFace.

| Variável de ambiente | Padrão | Efeito |
|---|---|---|
| `SOLARGAP_CARREGAR_MODELOS` | `1` | `0` não carrega os modelos (máquinas sem PyTorch; testes) |
| `SOLARGAP_DISPOSITIVO` | `auto` | `cuda` exige GPU; `cpu` força CPU |
| `SOLARGAP_TIMEOUT_INFERENCIA` | `60` | Segundos até a inferência responder **504** |
| `SOLARGAP_MODELO_RESUMO`, `SOLARGAP_MODELO_CLASSIFICACAO` | do catálogo | Troca o modelo por outra chave de `src/ia/catalogo.py` |

## Rotas

| Método | Rota | Função |
|---|---|---|
| GET | `/saude` | Verifica se a API está no ar e com dados carregados |
| GET | `/ufs` | Indicadores das 27 UFs no recorte, com a média nacional |
| GET | `/ufs/{sigla}` | Ficha da UF: indicadores, posições, crescimento, quadrante, ICMS, notícias |
| GET | `/ranking` | UFs ordenadas por uma métrica |
| GET | `/series/{sigla}` | Série anual, parque acumulado e crescimento anual da UF |
| GET | `/oportunidades` | Matriz adoção x crescimento, com o quadrante de cada UF |
| GET | `/potencial/uf` | Potencial (x), produção estimada (y), gap e % realizado das 27 UFs e do Brasil (TP4.5) |
| GET | `/potencial/municipio/{cod_ibge}` | Ficha de potencial de um município, com a taxa nas três visões (TP4.5) |
| GET | `/potencial/explicacao/{cod_ibge}` | Fatores associados à taxa de realização (SHAP), em linguagem simples (TP4.5) |
| GET | `/potencial/cenarios/{cod_ibge}` | Irradiação, x, y e gap em SSP2-4.5 e SSP5-8.5, 2030–2050, com faixa de incerteza (TP4.5) |
| GET | `/agente/status` | Provedor, modelo e se o LLM do agente está no ar (TP5) |
| **POST** | `/agente/perguntar` | **Pergunta ao agente de decisão: diagnóstico, fatores, recomendações e verificação dos números** (TP5) |
| GET | `/noticias` | Lista paginada e filtrável de notícias |
| GET | `/noticias/fontes` | Fontes do corpus, quantidade e nível de texto |
| GET | `/noticias/{id}` | Notícia completa, com `texto_para_modelo` (entrada dos modelos de linguagem) |
| **POST** | `/noticias` | **Envia uma nova notícia ao corpus** |
| GET | `/politicas/icms` | Adesão das 27 UFs ao Convênio ICMS 16/15 |
| GET | `/politicas/icms/{sigla}` | Adesão de uma UF |
| **POST** | `/comparacoes` | **Compara um indicador próprio por UF com a adoção solar** |
| GET | `/ia/status` | Estado de carga de cada modelo de linguagem (TP4) |
| **POST** | `/processar_texto` | **Resumo, relevância e tom (experimental) de um texto, com modelos locais** (TP4) |
| **POST** | `/noticias/{id}/processar` | **A mesma análise para uma notícia do corpus** (TP4) |

`GET /noticias` aceita também `relevante=true|false`, que filtra pela relevância estimada pelo modelo (notícias ainda não avaliadas ficam de fora).

### Filtros comuns (query string)

Aceitos por `/ufs`, `/ufs/{sigla}`, `/ranking`, `/series/{sigla}` e `/oportunidades`:

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `ano_inicio`, `ano_fim` | 2012, 2026 | Período de conexão (2026 é parcial) |
| `classes` | todas | Classe de consumo; repita o parâmetro: `?classes=Residencial&classes=Rural` |
| `incluir_imputados` | `true` | `true` é a visão corrigida: conta como solares os registros sem fonte informada (156 na base 10/2026) e usa a potência corrigida dos ~47 mil registros de 75 kW suspeitos. `false` reproduz o critério do painel oficial da ANEEL: sem esses registros imputados e com a potência oficial. (Até a base 08/2026, o parâmetro tratava só os ~73 mil registros sem fonte do MA.) |

`/ufs/{sigla}` e `/oportunidades` aceitam também `ano_base` e `ano_final` (janela do crescimento; padrão 2022–2025).

### Visão dos dados: dois parâmetros na API

A API tem hoje **dois parâmetros** para a visão da base ANEEL. O painel já usa as três visões em todas as páginas.

| Rotas | Parâmetro | Valores | Padrão | Visões |
|---|---|---|---|---|
| `/ufs`, `/ufs/{sigla}`, `/ranking`, `/series/{sigla}`, `/oportunidades` (query) e `POST /comparacoes` (campo do corpo) | `incluir_imputados` (booleano) | `true` · `false` | `true` | 2: corrigida e ANEEL |
| `/potencial/*` (TP4.5) | `visao` (texto) | `corrigida` · `aneel` · `conservadora` | `corrigida` | 3 |

Correspondência: `incluir_imputados=true` equivale a `visao=corrigida`, e `incluir_imputados=false` a `visao=aneel`. **O limite conservador não está disponível nas rotas de indicadores.**

Os erros também diferem. `incluir_imputados` aceita só booleano, e outro valor responde 422 na validação da FastAPI. `visao` fora da lista também responde 422, pelo enum `NomeVisao`.

O cálculo já está unificado: `src/servicos/indicadores.py` recebe a visão como texto (`corrigida`, `aneel` ou `conservadora`) e aceita o booleano antigo. A diferença está só na assinatura das rotas, mantida para não quebrar clientes do TP3 e do TP4. Ver a pendência em [Pendências](#pendências).

### Potencial solar (TP4.5)

As quatro rotas `/potencial` usam `src/servicos/potencial.py`, o mesmo código da página **Potencial Solar** do painel. Todas aceitam o parâmetro opcional `visao`:

| `visao` | O que muda |
|---|---|
| `corrigida` (padrão) | Imputa a potência dos ~47 mil registros de 75 kW da COPEL-DIS e conta como solares os 156 registros sem fonte |
| `aneel` | Dado oficial, sem correções, como o painel da agência |
| `conservadora` | Como a corrigida, mas imputa a potência só dos ~28 mil residenciais de 75 kW |

Valor fora da lista (inclusive com maiúsculas, como `ANEEL`) responde **422**. A visão muda só a produção estimada (y), o gap e a taxa; o potencial técnico (x) não depende da base da ANEEL. Nas agregações (UF, Brasil), a taxa é Σy / Σx.

- **`/potencial/uf`** devolve as 27 UFs, o total do Brasil, as premissas do cálculo (PR 0,75, eficiência 20%, 15 m² de telhado, base 10/2026) e, em cada UF, os três fatores de maior contribuição SHAP.
- **`/potencial/explicacao/{cod_ibge}`** explica a taxa do município em linguagem simples. **É associação, não causalidade.**
  - `fatores`: a contribuição SHAP de cada uma das 12 variáveis, do maior para o menor efeito, em fração e em pontos percentuais (`contribuicao_pp`), com o `grupo` e uma frase.
  - `grupos` (novo): soma as variáveis da mesma família, o que é válido porque o SHAP é aditivo. **Renda** = renda média + mediana (ρ = 0,98 entre elas), **Agropecuária** = peso no VAB + área ocupada, **Distribuidora e cooperativa** = mais de uma distribuidora + cooperativa (ρ = 0,84). As demais variáveis formam grupo próprio. Sem a soma, fatores correlacionados dividem o crédito de forma arbitrária.
  - `puxam_para_baixo` e `puxam_para_cima`: os grupos separados pelo sinal (até 3 de cada lado, com pelo menos 1 p.p.). Só os de contribuição negativa aparecem como "aumenta o gap".
  - `taxa_observada`, `taxa_prevista`, `diferenca_pp` (observada − prevista) e `comparacao_esperado`. Abaixo do esperado (diferença ≤ −0,5 p.p.) quer dizer que há espaço que os fatores medidos não explicam; acima (≥ +0,5 p.p.), que o município aproveita mais do que o perfil sugere.
  - `leitura`: junta a comparação e as duas listas.
  - Na UF e no Brasil, contribuições e previsão são médias ponderadas por domicílios, e a taxa observada é Σy / Σx.
  - Visões: o modelo foi treinado no alvo da visão corrigida, o único com explicação por município. Nas outras visões, as contribuições e a taxa prevista são as mesmas, `taxa_observada` é a da visão pedida, `aviso_visao` explica a diferença e `ranking_global_visao` traz os fatores mais importantes do modelo ajustado àquela visão (Tarefa 4, `docs/potencial/robustez_visoes.csv`).
- **`/potencial/cenarios/{cod_ibge}`** devolve, para SSP2-4.5 e SSP5-8.5 e as janelas 2030–2039 e 2040–2050, a variação da irradiação (mediana e faixa de 5 modelos do NEX-GDDP-CMIP6) e x, y e gap projetados, com a potência instalada fixa. A taxa do município não muda, porque a irradiação se cancela em y / x. **É um cenário com faixa de incerteza, não uma previsão.** A Gold traz y projetado das visões corrigida e ANEEL; o da conservadora é derivado pela razão da corrigida, exata no município. Metodologia em `docs/potencial/README.md`, seção "Projeção 2030–2050".

Erros: **404** para código IBGE inexistente, **422** para `visao` inválida e **503** se a Gold de potencial não estiver disponível. A Gold de potencial tem carga própria: sem ela, só as rotas `/potencial` respondem 503 e o resto da API segue no ar.

## Exemplos

**Consulta (GET) — as 5 UFs com maior adoção per capita:**

```bash
curl "http://127.0.0.1:8000/ranking?metrica=watts_por_habitante&limite=5"
```

```json
{
  "metrica": "watts_por_habitante",
  "rotulo": "Watts por habitante",
  "unidade": "W/hab",
  "ordem": "desc",
  "media_brasil": 249.67,
  "itens": [
    {"posicao": 1, "sigla_uf": "MT", "nome_uf": "Mato Grosso", "valor": 872.48, "...": "..."}
  ]
}
```

**Envio (POST) — nova notícia:**

```bash
curl -X POST "http://127.0.0.1:8000/noticias" -H "Content-Type: application/json" -d '{
  "fonte": "Prefeitura de Caxias do Sul",
  "url": "https://exemplo.org/noticia",
  "titulo": "Escolas municipais recebem painéis solares",
  "data_publicacao": "2026-10-01",
  "linha_fina": "Projeto no Rio Grande do Sul",
  "texto": null
}'
```

Resposta **201**: a notícia gravada, com `id`, `nivel_texto` (`integral` se houver texto; `metadados` se não), `ufs_mencionadas` detectadas automaticamente e `texto_para_modelo`. Ela é gravada em `data/external/noticias_enviadas.csv` (não versionado) e passa a aparecer no dashboard e em `GET /noticias`.

**Envio (POST) — comparação com indicador próprio:**

```bash
curl -X POST "http://127.0.0.1:8000/comparacoes" -H "Content-Type: application/json" -d '{
  "nome_indicador": "clientes",
  "valores": {"RS": 120, "SC": 85, "PR": 60, "SP": 40, "MT": 15}
}'
```

Resposta **200**: posição de cada UF no indicador do usuário e na métrica de adoção, `diferenca_posicoes` (positiva = presença abaixo do que a adoção sugere) e correlação de Spearman com interpretação.

**Consulta (GET) — fatores associados à taxa de Caxias do Sul (RS):**

```bash
curl "http://127.0.0.1:8000/potencial/explicacao/4305108?visao=aneel"
```

```json
{
  "nivel": "municipio",
  "nome": "Caxias do Sul (RS)",
  "cod_ibge": "4305108",
  "visao": "aneel",
  "visao_modelo": "corrigida",
  "taxa_observada": 0.0897,
  "taxa_prevista": 0.1081,
  "valor_base": 0.1448,
  "usado_no_treino": true,
  "diferenca_pp": -1.85,
  "comparacao_esperado": "Caxias do Sul (RS) realiza 9,0% no critério ANEEL; pelo perfil, o modelo esperaria 10,8%. Abaixo do esperado em 1,8 p.p.: há espaço que os fatores medidos não explicam.",
  "leitura": "Caxias do Sul (RS) realiza 9,0% no critério ANEEL; pelo perfil, o modelo esperaria 10,8%. Abaixo do esperado em 1,8 p.p.: há espaço que os fatores medidos não explicam. O que mais puxa a taxa para baixo (aumenta o gap): densidade demográfica (−7,7 p.p.), agropecuária (−3,8 p.p.) e população (−1,5 p.p.). O que mais puxa a taxa para cima (reduz o gap): renda (+11,0 p.p.).",
  "aviso_visao": "As contribuições SHAP vêm do modelo treinado na visão corrigida, o único com explicação por município. ...",
  "puxam_para_baixo": ["Densidade demográfica", "Agropecuária", "População"],
  "puxam_para_cima": ["Renda"],
  "grupos": [
    {
      "grupo": "renda",
      "rotulo": "Renda",
      "fatores": ["renda_domiciliar_pc_media", "renda_domiciliar_pc_mediana"],
      "contribuicao": 0.1095,
      "contribuicao_pp": 10.95,
      "efeito": "eleva"
    },
    {"grupo": "log_densidade_hab_km2", "rotulo": "Densidade demográfica", "contribuicao_pp": -7.71, "efeito": "reduz", "...": "..."}
  ],
  "fatores": [
    {
      "fator": "log_densidade_hab_km2",
      "grupo": "log_densidade_hab_km2",
      "rotulo": "Densidade demográfica",
      "rotulo_no_grupo": "Densidade demográfica",
      "valor": 280.52,
      "valor_texto": "280,5 hab/km²",
      "contribuicao": -0.0771,
      "contribuicao_pp": -7.71,
      "efeito": "reduz",
      "frase": "Densidade demográfica, 280,5 hab/km²: reduz a taxa prevista em 7,7 p.p."
    },
    {"fator": "renda_domiciliar_pc_media", "grupo": "renda", "rotulo_no_grupo": "Renda · média", "contribuicao_pp": 5.57, "efeito": "eleva", "...": "..."}
  ],
  "ranking_global_visao": ["Densidade demográfica", "Renda domiciliar per capita (média)", "Renda domiciliar per capita (mediana)", "Peso da agropecuária na economia (VAB)", "Irradiação solar"]
}
```

Caxias do Sul não é atendida pela COPEL-DIS nem tem registros sem fonte: a taxa é a mesma nas três visões. A visão muda só `aviso_visao`, `ranking_global_visao` e o trecho "no critério ANEEL" das frases.

Em `/potencial/uf`, `principais_fatores` traz os três grupos de maior efeito absoluto na UF, com o sinal: `"Renda (+8,6 p.p.)"`.

## Modelos de linguagem (TP4)

Modelos escolhidos por benchmark (`docs/escolha_modelo.md`):

| Tarefa | Modelo | Observação |
|---|---|---|
| `resumo` | `recogna-nlp/ptt5-base-summ` | Resumo abstrativo em português |
| `relevancia` | `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` | Zero-shot: "Esta notícia trata de energia solar." Relevante se a probabilidade for ≥ 0,5 |
| `tom` | mesmo mDeBERTa | **Experimental**: ficou abaixo da linha de base no benchmark; a resposta traz `experimental: true` e um aviso |

**`POST /processar_texto`**

```bash
curl -X POST http://127.0.0.1:8000/processar_texto \
  -H "Content-Type: application/json" \
  -d '{"texto": "A potência instalada de micro e minigeração distribuída solar no Brasil ultrapassou 40 GW, segundo a ANEEL. Minas Gerais lidera.", "tarefas": ["resumo", "relevancia"]}'
```

```json
{
  "origem": "texto",
  "tarefas": ["resumo", "relevancia"],
  "caracteres_entrada": 135,
  "resultados": {
    "resumo": {"resumo": "...", "tokens_entrada": 41, "truncado": false},
    "relevancia": {"relevante": true, "probabilidade": 0.998, "limiar": 0.5, "tokens_entrada": 41, "truncado": false}
  },
  "modelos": [
    {"tarefa": "resumo", "modelo": "recogna-nlp/ptt5-base-summ", "licenca": "MIT"},
    {"tarefa": "relevancia", "modelo": "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7", "licenca": "MIT"}
  ],
  "dispositivo": "cuda",
  "duracao_ms": 2140
}
```

- **Entrada:** `texto` com 40 a 20.000 caracteres e pelo menos 8 palavras; `tarefas` opcional (padrão: `resumo` e `relevancia`), sem repetição.
- **Truncamento:** os modelos leem até 512 tokens (~350 palavras). Acima disso, leem o início e a resposta traz `truncado: true`.
- **Só aparecem na resposta** os resultados das tarefas pedidas.

**`POST /noticias/{id}/processar?tarefas=resumo&tarefas=tom`** usa como entrada o `texto_para_modelo` da notícia, a mesma do processamento em lote (`python -m src.ia.processar_corpus`).

## Agente de decisão (TP5)

`POST /agente/perguntar` recebe uma pergunta em português e devolve a resposta em markdown com a trilha completa: recorte identificado, intenções, ferramentas usadas (com os fatos e os dados brutos de cada uma), ações recomendadas e verificação dos números. Sem LLM no ar, a rota **não falha**: responde no modo por regras (`"modo": "regras"`) e informa em `avisos`. Metodologia em [`docs/agente/README.md`](agente/README.md).

```bash
curl -X POST http://127.0.0.1:8000/agente/perguntar \
  -H "Content-Type: application/json" \
  -d '{"pergunta": "Por que Caxias do Sul está abaixo do esperado e o que fazer?"}'
```

Resposta (trecho):

```json
{
  "modo": "llm",
  "modelo": "qwen2.5:7b via ollama",
  "intencoes": ["explicacao"],
  "recorte": {"nivel": "municipio", "uf": "RS", "cod_ibge": "4305108", "descricao": "Caxias do Sul (RS)"},
  "ferramentas": [{"nome": "resumo_potencial", "fatos": ["Caxias do Sul (RS): taxa de realização de 9,0% (Brasil: 10,4%)."]}],
  "acoes": [{"fator": "Densidade demográfica", "nivel": "alto", "acao": "Densidade alta indica mais apartamentos..."}],
  "verificacao": {"numeros": 12, "verificados": 12, "nao_encontrados": [], "taxa": 1.0},
  "contexto": {"recorte": {"nivel": "municipio", "cod_ibge": "4305108"}}
}
```

**Memória.** Para uma pergunta de seguimento ("E os cenários climáticos?"), envie `historico` (lista de `{pergunta, resposta}`) e o `contexto` da resposta anterior. O recorte é herdado e a resposta traz `recorte_herdado: true`.

**Parâmetros do corpo:** `pergunta` (3 a 1.000 caracteres), `historico` (até 20 trocas), `contexto`, `visao` (corrigida, aneel ou conservadora) e `usar_llm` (false força o modo por regras).

## Códigos de resposta

Todas as respostas de erro têm o formato `{"detail": "..."}`.

| Código | Quando | Exemplo |
|---|---|---|
| 200 / 201 | Sucesso / notícia criada | — |
| 400 | Filtros incoerentes | `ano_inicio` maior que `ano_fim`; classe inexistente; janela de crescimento inválida |
| 404 | Recurso inexistente | `/ufs/XX`, `/noticias/abc`, `/potencial/municipio/9999999` |
| 409 | Conflito | `POST /noticias` com URL já existente no corpus |
| 422 | Validação dos dados enviados | `visao` fora de corrigida, aneel e conservadora; URL inválida, título com menos de 10 caracteres, data no futuro, UF inválida, menos de 3 UFs na comparação. O `detail` lista cada campo com problema |
| 503 | Dados ou modelo indisponíveis | Arquivo obrigatório da Gold ausente (nas rotas `/potencial`, a Gold de potencial); modelo de linguagem **carregando** (com `Retry-After: 30`), **não carregado** ou com **falha de carga** (o `detail` traz o erro). Uma falha em um modelo não afeta as tarefas do outro |
| 504 | Tempo esgotado | Inferência acima de `SOLARGAP_TIMEOUT_INFERENCIA` segundos |
| 500 | Erro inesperado | Registrado no log; o cliente recebe mensagem genérica, sem rastro de pilha |

## Pendências

- **Unificar o parâmetro de visão (TP5).** Acrescentar `visao` (`corrigida` | `aneel` | `conservadora`) às rotas de indicadores e a `POST /comparacoes`, com o mesmo enum `NomeVisao` das rotas `/potencial`. Manter `incluir_imputados` por uma versão como alias obsoleto (`deprecated` no OpenAPI); se os dois vierem juntos e divergirem, responder 400. Depois, remover o alias numa versão 2.0. Até lá, o limite conservador só existe nas rotas `/potencial` e no painel.

## Preparação para os próximos TPs

- **TP4 (concluído):** rotas de IA em `src/api/rotas/ia.py`, com modelos de resposta, 503 e 504. A inferência roda em uma thread, com uma inferência por vez (fila), para não disputar a memória da GPU; enquanto isso, as demais rotas continuam respondendo.
- **TP5 (concluído):** rotas `/agente`. As ferramentas do agente chamam a mesma camada de serviços das rotas `/potencial` e de indicadores, sem HTTP. Os números são idênticos aos da API, e o agente funciona mesmo dentro do painel, com a API fora do ar.

## Testes

`tests/test_api.py`, `tests/test_api_potencial.py`, `tests/test_ia_api.py` e `tests/test_api_agente.py` cobrem todas as rotas e todos os códigos de erro acima com o `TestClient` da FastAPI. As rotas de IA usam um gerenciador de modelos falso, que simula carga lenta, falha de carga e inferência demorada sem PyTorch e sem download; a inferência real é testada em `tests/test_ia.py` com modelos minúsculos criados na hora. As gravações vão para uma pasta temporária.

```bash
python -m pytest tests/test_api.py tests/test_api_potencial.py tests/test_ia_api.py
```
