# app/processing — processamento de dados

Todo o código que transforma dados (documentos, CSVs, regras e chamadas à IA) fica
aqui, separado por etapa. As rotas em `app/api` só recebem a requisição e chamam
estas pastas; o banco (`app/db`) e os contratos (`app/schemas`) continuam fora.

```
processing/
├── shared/      armazenamento de arquivos e normalização de texto (base de tudo)
├── documents/   PDF/HTML/TXT → PDF + texto com posições; download seguro; destaques
├── datasets/    CSV → colunas tipadas → cache DuckDB → consultas SQL paginadas
├── ai/          Gemini: extrair regras, gerar buscas, chat, interpretar colunas/planos
├── rules/       buscas por regra e verificação de conformidade sobre as bases
└── pipeline/    ingest.py: tarefas asyncio que encadeiam as etapas acima
```

## Dependências entre as pastas

Uma pasta só importa as que estão abaixo dela nesta lista. Mantenha essa direção ao
editar; assim cada etapa pode ser medida, trocada ou removida isoladamente.

| Pasta | Usa | É usada por |
| --- | --- | --- |
| `shared` | — | todas |
| `documents` | `shared` | `pipeline`, rotas de documentos |
| `datasets` | `shared` | `rules`, `pipeline`, rotas de análises |
| `ai` | — (`llm_mock` usa `shared`) | `rules`, `pipeline`, chat |
| `rules` | `ai`, `datasets` | `pipeline`, rotas de regras/validação |
| `pipeline` | todas | `app/main.py` (recuperação) e rotas |

## O que cada etapa faz e onde ela é acionada

| Etapa | Arquivos | Acionada em (`pipeline/ingest.py`) | Custo típico |
| --- | --- | --- | --- |
| Conversão de documento | `documents/converters/*`, `document_upload.py` | `process_document` → `document_upload.convert_source` | CPU (render HTML → PDF) |
| Extração de texto/posições | `documents/pdf_text.py` | `process_document` → `extract_pdf` | CPU, proporcional às páginas |
| Destaques das regras | `documents/highlights.py`, `text_match.py` | rotas em `api/v1/documents.py` | baixo |
| Download por URL | `documents/safe_fetch.py` | rota de criação por link | rede |
| Leitura do CSV | `datasets/datasets.py` | `process_dataset` → `parse_csv` | CPU, proporcional às linhas |
| Cache DuckDB | `datasets/duckdb_cache.py`, `query_engine.py` | `process_dataset` → `prime_dataset` | disco + CPU na importação |
| Consultas SQL | `datasets/duckdb_sql.py`, `query_engine.py` | `rules/rule_queries.records` | depende do filtro e do volume |
| Interpretação das colunas | `ai/validation_llm.py` | `process_dataset` → `rule_validation.interpret` | chamada ao Gemini |
| Extração de regras | `ai/llm.py` | `process_document` → `llm.extract_rules` | chamadas ao Gemini por bloco |
| Geração das buscas | `rules/rule_queries.py` + `ai/llm.py` | `_generate_queries` | chamada ao Gemini por regra |
| Validação de conformidade | `rules/rule_validation.py`, `compliance.py` + `ai/validation_llm.py` | `_run_validation` (só sob pedido) | Gemini + consultas DuckDB |

## Removendo ou desligando uma funcionalidade

1. Localize a chamada na coluna "Acionada em" e remova-a (ou proteja com uma
   configuração em `app/core/config.py`).
2. Remova as rotas correspondentes em `app/api/v1/` e o uso no frontend.
3. Só então apague a pasta/arquivo; use a tabela de dependências para conferir que
   nenhuma pasta acima dela ainda o importa (`grep -rn "processing.<pasta>" app tests`).

Exemplos:

- **Sem validação de conformidade:** retire `start_validation`/`_run_validation` do
  `ingest.py` e as rotas de validação; `rules/compliance.py`, `rules/rule_validation.py`
  e `ai/validation_llm.py` deixam de ser necessários (mantenha `interpret` se ainda
  quiser os significados das colunas).
- **Somente PDF:** em `documents/converters/registry.py`, registre só o `PdfConverter`.
  `html.py`, `text.py` e `render.py` podem sair.
- **Sem IA:** `LLM_MOCK=true` já substitui o Gemini por respostas prontas
  (`ai/llm_mock.py`), útil para medir o restante do fluxo sem latência de rede.

## Medindo desempenho por etapa

`app/core/logging.py` fornece `log_step`, que registra a duração de um bloco.
Envolva a chamada da etapa no `ingest.py` para compará-las. Os testes de desempenho
existentes servem de referência para cada pasta:

| Pasta | Testes |
| --- | --- |
| `documents` | `tests/test_document_upload_performance.py`, `test_highlight_performance.py`, `test_converters.py` |
| `datasets` | `tests/test_duckdb_cache.py`, `test_datasets.py`, `test_queries.py` |
| `rules` | `tests/test_processing_performance.py`, `test_compliance.py`, `test_prepared_queries.py` |
| `ai` | `tests/test_llm.py`, `test_llm_limits.py` |
| `pipeline` | `tests/test_ingest_performance.py`, `test_close_analysis.py` |
