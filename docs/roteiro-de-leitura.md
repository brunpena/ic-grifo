# Roteiro para estudar o código

[Índice](README.md) · [Arquitetura](arquitetura.md) · [Fluxogramas](fluxos.md)

A melhor unidade de estudo é uma operação completa. Abra a tela que inicia a operação,
o hook que faz a requisição, a rota que recebe o pedido e o serviço que executa a regra
de negócio. Use os mapas de arquivos para consultar detalhes sem ler tudo de uma vez.

## 1. Entenda o vocabulário antes dos componentes

Leia a [arquitetura](arquitetura.md). Depois abra
[models.py](../backend/app/db/models.py) e localize `Analysis`, `Dataset`, `Document`,
`Rule` e `RuleQuery`.

Ao terminar, você deve conseguir explicar por que uma análise pode ter vários
documentos e várias bases, por que a regra pertence a um documento e por que uma busca
não é o mesmo objeto que uma validação.

## 2. Descubra como o projeto inicia

Abra, nesta ordem:

1. [package.json da raiz](../package.json): veja os scripts `dev`, `dev:backend` e `dev:frontend`.
2. [dev-backend.mjs](../scripts/dev-backend.mjs): siga a decisão sobre Docker, migrations e watchfiles.
3. [main.py](../backend/app/main.py): leia `create_app` e `lifespan`.
4. [router.py](../backend/app/api/v1/router.py): veja o prefixo e os grupos de endpoints.
5. [layout.tsx](../frontend/src/app/layout.tsx) e [providers.tsx](../frontend/src/app/providers.tsx):
   localize estilos, tema, TanStack Query e notificações.
6. [app-shell.tsx](../frontend/src/components/app/app-shell.tsx): encontre a consulta da sessão e a navegação.

Repare que inicializar a API e aplicar migrations são ações diferentes: os scripts de
execução fazem a migration, enquanto `create_app` monta a aplicação.

## 3. Siga o envio de uma base CSV

Percorra [dataset-uploader.tsx](../frontend/src/components/datasets/dataset-uploader.tsx)
→ [analyses.ts](../frontend/src/lib/analyses.ts)
→ [analyses.py](../backend/app/api/v1/analyses.py), função `upload_dataset`
→ [ingest.py](../backend/app/services/ingest.py), função `process_dataset`.

Depois leia [datasets.py](../backend/app/services/datasets.py), especialmente
`parse_csv`, `infer_column` e `parse_value`, e
[validation_llm.py](../backend/app/services/validation_llm.py), função `interpret_columns`.

Responda: o que já aconteceu quando o POST devolve 202? O que ainda falta? O que fica
no banco e o que fica apenas no arquivo? Por que uma base pode estar pronta para leitura
e, mesmo assim, ter o significado de uma coluna não confirmado?

## 4. Siga a entrada de um documento até o grifo

Comece em [assistant-view.tsx](../frontend/src/components/assistant/assistant-view.tsx),
nas funções `openFiles`, `ensureAnalysis` e `openDocument`.

Depois percorra [documents.ts](../frontend/src/lib/documents.ts)
→ [documents.py](../backend/app/api/v1/documents.py), função `_create_document`
→ [registry.py](../backend/app/services/converters/registry.py)
→ [pdf_text.py](../backend/app/services/pdf_text.py)
→ [ingest.py](../backend/app/services/ingest.py), função `process_document`.

Finalize com `extract_rules` em [llm.py](../backend/app/services/llm.py),
`rule_boxes` em [highlights.py](../backend/app/services/highlights.py) e
[highlight-layer.tsx](../frontend/src/components/document/highlight-layer.tsx).

A pergunta central é: como uma regra encontrada em texto se transforma em retângulos
sobre uma página PDF? O [fluxograma de documentos](fluxos.md) ajuda a seguir a resposta.

## 5. Compare busca e validação usando a mesma regra

Use o [exemplo de validação](validacao.md). Primeiro leia
[schemas/queries.py](../backend/app/schemas/queries.py),
[rule_queries.py](../backend/app/services/rule_queries.py) e
[query_engine.py](../backend/app/services/query_engine.py).

Em seguida leia [schemas/validation.py](../backend/app/schemas/validation.py),
[rule_validation.py](../backend/app/services/rule_validation.py) e
[compliance.py](../backend/app/services/compliance.py).

Compare os objetos retornados por `compile_query` e `compile_validation`. A busca
seleciona linhas. A validação combina escopo, critérios, significado das colunas e dados
faltantes para atribuir resultados. Não confunda `Rule.status` com `Rule.validation.status`.

## 6. Veja como os resultados chegam à pessoa

Abra [validation.ts](../frontend/src/lib/validation.ts),
[validation-badge.tsx](../frontend/src/components/validation/validation-badge.tsx),
[validation-details.tsx](../frontend/src/components/validation/validation-details.tsx) e
[records-panel.tsx](../frontend/src/components/records/records-panel.tsx).

Volte ao Assistente e localize `rulesPanel`, `tablePanel` e `goToRule`. Observe como
selecionar uma regra sincroniza a tabela, os registros e o documento.

## 7. Estude o chat e a sessão

Para o chat, siga `send` no Assistente → `streamMessage` em `documents.ts`
→ `send_message` em `documents.py` → `stream_chat` em `llm.py`.
Identifique os eventos `delta`, `done` e `error`.

Para a sessão, siga [auth.ts](../frontend/src/lib/auth.ts)
→ [auth.py](../backend/app/api/v1/auth.py)
→ [security.py](../backend/app/core/security.py)
→ [deps.py](../backend/app/api/deps.py).

Diferencie a proteção visual de `AppShell` da verificação de usuário e proprietário
feita pelo backend.

## 8. Use os testes como exemplos executáveis

| Quero ver um exemplo de | Leia |
| --- | --- |
| Enviar e interpretar CSV | [test_datasets.py](../backend/tests/test_datasets.py) |
| Documento, grifos e conversa | [test_documents.py](../backend/tests/test_documents.py) |
| Regra transformada em filtro | [test_queries.py](../backend/tests/test_queries.py) |
| Datas, percentuais e valores ausentes | [test_compliance.py](../backend/tests/test_compliance.py) |
| Validação completa, permissões e concorrência | [test_validation_api.py](../backend/tests/test_validation_api.py) |

Leia a preparação da fixture, a chamada à operação e as asserções. Antes de executar
testes com banco, confira as instruções de [desenvolvimento](desenvolvimento.md).
