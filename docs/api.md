# API — SolarGap Brasil

**Versão:** 1.0.0 (TP3) · **Tecnologia:** FastAPI + Pydantic · **Código:** `src/api/`

A API expõe a camada Gold do projeto (ANEEL + IBGE), o corpus de notícias e a adesão ao Convênio ICMS 16/15. Os cálculos vêm de `src/servicos/` — os mesmos usados pelo dashboard, portanto os números são idênticos nos dois canais.

## Como executar

```bash
uvicorn src.api.main:app --reload
```

- Documentação interativa (Swagger): http://127.0.0.1:8000/docs — permite testar cada rota no navegador
- Documentação alternativa (ReDoc): http://127.0.0.1:8000/redoc
- Esquema OpenAPI: http://127.0.0.1:8000/openapi.json

Os dados são lidos **uma vez**, no startup. Se faltar um arquivo obrigatório da Gold, a API sobe mesmo assim e responde **503** com a instrução de correção.

## Rotas

| Método | Rota | Função |
|---|---|---|
| GET | `/saude` | Verifica se a API está no ar e com dados carregados |
| GET | `/ufs` | Indicadores das 27 UFs no recorte, com a média nacional |
| GET | `/ufs/{sigla}` | Ficha da UF: indicadores, posições, crescimento, quadrante, ICMS, notícias |
| GET | `/ranking` | UFs ordenadas por uma métrica |
| GET | `/series/{sigla}` | Série anual, parque acumulado e crescimento anual da UF |
| GET | `/oportunidades` | Matriz adoção x crescimento, com o quadrante de cada UF |
| GET | `/noticias` | Lista paginada e filtrável de notícias |
| GET | `/noticias/fontes` | Fontes do corpus, quantidade e nível de texto |
| GET | `/noticias/{id}` | Notícia completa, com `texto_para_modelo` (entrada do LLM no TP4) |
| **POST** | `/noticias` | **Envia uma nova notícia ao corpus** |
| GET | `/politicas/icms` | Adesão das 27 UFs ao Convênio ICMS 16/15 |
| GET | `/politicas/icms/{sigla}` | Adesão de uma UF |
| **POST** | `/comparacoes` | **Compara um indicador próprio por UF com a adoção solar** |

### Filtros comuns (query string)

Aceitos por `/ufs`, `/ufs/{sigla}`, `/ranking`, `/series/{sigla}` e `/oportunidades`:

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `ano_inicio`, `ano_fim` | 2012, 2026 | Período de conexão (2026 é parcial) |
| `classes` | todas | Classe de consumo; repita o parâmetro: `?classes=Residencial&classes=Rural` |
| `incluir_imputados` | `true` | `false` reproduz o critério do painel oficial da ANEEL (exclui os ~73 mil registros sem fonte do MA) |

`/ufs/{sigla}` e `/oportunidades` aceitam também `ano_base` e `ano_final` (janela do crescimento; padrão 2022–2025).

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
  "media_brasil": 252.75,
  "itens": [
    {"posicao": 1, "sigla_uf": "MT", "nome_uf": "Mato Grosso", "valor": 863.3, "...": "..."}
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

## Códigos de resposta

Todas as respostas de erro têm o formato `{"detail": "..."}`.

| Código | Quando | Exemplo |
|---|---|---|
| 200 / 201 | Sucesso / notícia criada | — |
| 400 | Filtros incoerentes | `ano_inicio` maior que `ano_fim`; classe inexistente; janela de crescimento inválida |
| 404 | Recurso inexistente | `/ufs/XX`, `/noticias/abc` |
| 409 | Conflito | `POST /noticias` com URL já existente no corpus |
| 422 | Validação dos dados enviados | URL inválida, título com menos de 10 caracteres, data no futuro, UF inválida, menos de 3 UFs na comparação. O `detail` lista cada campo com problema |
| 503 | Dados indisponíveis | Arquivo obrigatório da Gold ausente; tabela de ICMS ainda não gerada |
| 500 | Erro inesperado | Registrado no log; o cliente recebe mensagem genérica, sem rastro de pilha |

## Preparação para os próximos TPs

- **TP4 (LLM local):** os modelos de resposta (`response_model`) e o tratamento de erros já seguem o padrão exigido. A rota `POST /processar_texto` será um novo módulo em `src/api/rotas/`. Ela receberá o `texto_para_modelo` e responderá **503** se o modelo não estiver carregado. O resultado vai para as colunas `resumo` e `sentimento`, já presentes no esquema.
- **TP5 (agente):** as rotas GET são as ferramentas naturais do agente. `/ufs/{sigla}` reúne em uma chamada tudo o que uma recomendação sobre um estado precisa.

## Testes

`tests/test_api.py` cobre todas as rotas e todos os códigos de erro acima com o `TestClient` da FastAPI. As gravações vão para uma pasta temporária.

```bash
python -m pytest tests/test_api.py
```
