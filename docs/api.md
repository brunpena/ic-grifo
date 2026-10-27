# Referência da API e conexão com a interface

[Índice](README.md) · [Fluxos](fluxos.md) · [Backend](backend.md)

O contrato executável é produzido por FastAPI em `/openapi.json`. A documentação
interativa está em `/docs`. As tabelas desta página foram conferidas com os decoradores
das rotas em `backend/app/api/v1`; não incluem as rotas internas de documentação do FastAPI.

## Regras comuns

- A base de desenvolvimento é `http://localhost:8000`; as rotas de negócio usam `/api/v1`.
- Autenticação usa cookie de sessão. O cliente chama a API com `credentials: "include"`.
- O backend verifica o proprietário do recurso, não apenas a existência de uma sessão.
- HTTP 202 indica processamento assíncrono; acompanhe o campo `status` depois.
- HTTP 204 não devolve conteúdo para a interface consumir.
- IDs de análise, documento, base e regra são UUIDs.
- A URL em `NEXT_PUBLIC_API_URL` é a base do servidor, sem repetir `/api/v1`.

## Onde a interface chama cada família

| Família | Hooks e cliente | Arquivo de rotas |
| --- | --- | --- |
| Sessão e perfil | [auth.ts](../frontend/src/lib/auth.ts) | [auth.py](../backend/app/api/v1/auth.py) |
| Análises e CSVs | [analyses.ts](../frontend/src/lib/analyses.ts) | [analyses.py](../backend/app/api/v1/analyses.py) |
| Documentos, regras e chat | [documents.ts](../frontend/src/lib/documents.ts) | [documents.py](../backend/app/api/v1/documents.py) |
| Buscas e registros | [queries.ts](../frontend/src/lib/queries.ts) | [documents.py](../backend/app/api/v1/documents.py) |
| Cumprimento e evidência | [validation.ts](../frontend/src/lib/validation.ts) | [documents.py](../backend/app/api/v1/documents.py) |

O transporte tipado fica em [client.ts](../frontend/src/lib/api/client.ts).
Uploads de CSV usam XMLHttpRequest para progresso; o chat usa fetch para ler SSE.


## Autenticação e perfil

| Método e caminho | Função | Sucesso | Acesso | Efeito |
| --- | --- | --- | --- | --- |
| `POST /api/v1/auth/register` | [register](<../backend/app/api/v1/auth.py>) | 201 | Público | Cria uma conta e já inicia a sessão |
| `POST /api/v1/auth/login` | [login](<../backend/app/api/v1/auth.py>) | 200 | Público | Entra com e-mail e senha |
| `POST /api/v1/auth/logout` | [logout](<../backend/app/api/v1/auth.py>) | 204 | Opcional | Encerra a sessão atual |
| `GET /api/v1/auth/me` | [me](<../backend/app/api/v1/auth.py>) | 200 | Sessão exigida | Usuário da sessão atual |
| `PATCH /api/v1/me` | [update_profile](<../backend/app/api/v1/auth.py>) | 200 | Sessão exigida | Atualiza o perfil |
| `POST /api/v1/me/password` | [change_password](<../backend/app/api/v1/auth.py>) | 204 | Sessão exigida | Troca a senha e encerra as outras sessões |

## Análises e bases

| Método e caminho | Função | Sucesso | Acesso | Efeito |
| --- | --- | --- | --- | --- |
| `POST /api/v1/analyses` | [create_analysis](<../backend/app/api/v1/analyses.py>) | 201 | Sessão exigida | Cria uma análise vazia (as bases e os documentos são enviados depois) |
| `GET /api/v1/analyses` | [list_analyses](<../backend/app/api/v1/analyses.py>) | 200 | Sessão exigida | Análises do usuário, da mais recente à mais antiga |
| `GET /api/v1/analyses/{analysis_id}` | [get_analysis](<../backend/app/api/v1/analyses.py>) | 200 | Sessão exigida | A análise com suas bases e documentos |
| `PATCH /api/v1/analyses/{analysis_id}` | [update_analysis](<../backend/app/api/v1/analyses.py>) | 200 | Sessão exigida | Renomeia a análise |
| `DELETE /api/v1/analyses/{analysis_id}` | [delete_analysis](<../backend/app/api/v1/analyses.py>) | 204 | Sessão exigida | Exclui a análise, com as bases, os documentos, as regras e as conversas |
| `POST /api/v1/analyses/{analysis_id}/datasets` | [upload_dataset](<../backend/app/api/v1/analyses.py>) | 202 | Sessão exigida | Envia uma base de dados em CSV; o servidor lê em segundo plano |
| `GET /api/v1/datasets/{dataset_id}` | [get_dataset](<../backend/app/api/v1/analyses.py>) | 200 | Sessão exigida | Schema e situação da leitura de uma base |
| `DELETE /api/v1/datasets/{dataset_id}` | [delete_dataset](<../backend/app/api/v1/analyses.py>) | 204 | Sessão exigida | Remove a base da análise |

## Documentos, regras, buscas, validação e conversa

| Método e caminho | Função | Sucesso | Acesso | Efeito |
| --- | --- | --- | --- | --- |
| `POST /api/v1/documents` | [upload_document](<../backend/app/api/v1/documents.py>) | 202 | Sessão exigida | Envia um arquivo (PDF, HTML ou TXT); a extração de regras continua em segundo plano |
| `POST /api/v1/documents/text` | [create_text_document](<../backend/app/api/v1/documents.py>) | 202 | Sessão exigida | Cria um documento a partir de texto colado |
| `POST /api/v1/documents/url` | [create_url_document](<../backend/app/api/v1/documents.py>) | 202 | Sessão exigida | Baixa um documento (PDF ou página HTML) a partir de um link |
| `GET /api/v1/documents` | [list_documents](<../backend/app/api/v1/documents.py>) | 200 | Sessão exigida | Documentos do usuário, do mais recente ao mais antigo |
| `GET /api/v1/documents/{document_id}` | [get_document](<../backend/app/api/v1/documents.py>) | 200 | Sessão exigida | Status do documento |
| `GET /api/v1/documents/{document_id}/file` | [get_document_file](<../backend/app/api/v1/documents.py>) | 200 | Sessão exigida | O PDF original |
| `DELETE /api/v1/documents/{document_id}` | [delete_document](<../backend/app/api/v1/documents.py>) | 204 | Sessão exigida | Exclui o documento, as regras e a conversa |
| `GET /api/v1/documents/{document_id}/rules` | [list_rules](<../backend/app/api/v1/documents.py>) | 200 | Sessão exigida | Regras do documento, na ordem do texto |
| `POST /api/v1/documents/{document_id}/rules` | [create_rule](<../backend/app/api/v1/documents.py>) | 201 | Sessão exigida | Cria uma regra a partir de um trecho selecionado na página |
| `PATCH /api/v1/rules/{rule_id}` | [update_rule](<../backend/app/api/v1/documents.py>) | 200 | Sessão exigida | Atualiza situação, tipo, resumo ou comentário |
| `DELETE /api/v1/rules/{rule_id}` | [delete_rule](<../backend/app/api/v1/documents.py>) | 204 | Sessão exigida | Exclui a regra |
| `POST /api/v1/documents/{document_id}/queries` | [generate_document_queries](<../backend/app/api/v1/documents.py>) | 202 | Sessão exigida | Gera com a IA as buscas das regras nas bases da análise (em segundo plano) |
| `PUT /api/v1/rules/{rule_id}/query` | [set_rule_query](<../backend/app/api/v1/documents.py>) | 200 | Sessão exigida | Define (ou corrige) a busca da regra e roda de novo |
| `POST /api/v1/rules/{rule_id}/query/run` | [run_rule_query](<../backend/app/api/v1/documents.py>) | 200 | Sessão exigida | Roda de novo a busca da regra (ex.: depois de reenviar a base) |
| `DELETE /api/v1/rules/{rule_id}/query` | [delete_rule_query](<../backend/app/api/v1/documents.py>) | 204 | Sessão exigida | Remove a busca da regra |
| `GET /api/v1/rules/{rule_id}/records` | [list_rule_records](<../backend/app/api/v1/documents.py>) | 200 | Sessão exigida | Registros da base encontrados pela busca da regra, paginados |
| `POST /api/v1/documents/{document_id}/validation` | [validate_document](<../backend/app/api/v1/documents.py>) | 202 | Sessão exigida | Interpreta as colunas e verifica todas as regras do documento nas bases |
| `GET /api/v1/rules/{rule_id}/validation/records` | [validation_records](<../backend/app/api/v1/documents.py>) | 200 | Sessão exigida | Registros verificados, com resultado e evidência de cada linha |
| `GET /api/v1/documents/{document_id}/messages` | [list_messages](<../backend/app/api/v1/documents.py>) | 200 | Sessão exigida | Histórico da conversa sobre o documento |
| `POST /api/v1/documents/{document_id}/messages` | [send_message](<../backend/app/api/v1/documents.py>) | 200 | Sessão exigida | Pergunta sobre o documento; a resposta chega por SSE |

## Saúde

| Método e caminho | Função | Sucesso | Acesso | Efeito |
| --- | --- | --- | --- | --- |
| `GET /api/v1/health` | [health](<../backend/app/api/v1/health.py>) | 200 | Público | Verifica se a API e o banco respondem |


## Entradas e saídas dos fluxos principais

| Operação | Entrada | Saída |
| --- | --- | --- |
| Criar análise | JSON `AnalysisCreateIn`, título opcional | `AnalysisDetailOut` |
| Enviar CSV | Multipart, campo `file` | `DatasetOut` inicialmente em processing |
| Enviar documento | Multipart `file` e `analysis_id` opcional | `DocumentOut` |
| Colar texto | JSON `TextDocumentIn`: content, análise e título opcionais | `DocumentOut` |
| Usar link | JSON `UrlDocumentIn`: url e análise opcional | `DocumentOut` |
| Criar regra manual | JSON `RuleCreateIn`: type, summary, page e excerpt | `RuleOut` |
| Atualizar regra | JSON `RuleUpdateIn`: campos da revisão/tipo/resumo/comentário | `RuleOut` |
| Gerar buscas | JSON `GenerateQueriesIn`: overwrite | `DocumentOut`, depois consultar regras |
| Definir busca | JSON `StructuredQuery` | `RuleOut` após validar e executar o filtro |
| Validar cumprimento | Sem corpo; query `refresh_columns` opcional | `DocumentOut`, depois consultar regras |
| Enviar pergunta | JSON `MessageIn`: content | Streaming SSE |

Sem `analysis_id`, um novo documento recebe uma análise criada pelo backend.
HTML/TXT são convertidos; o endpoint de arquivo devolve o PDF usado pelo visualizador.

A geração de buscas exige ao menos uma base pronta. A validação geral pode registrar
regras como inconclusivas quando não há bases. Regras em documentos ainda em
processamento não estão prontas para conversa ou edição.

## Paginação de registros

- A busca existente usa `GET /api/v1/rules/{rule_id}/records`.
- A evidência de cumprimento usa `GET /api/v1/rules/{rule_id}/validation/records`.
- Ambos aceitam `offset >= 0` e `limit` de 1 a 500; o padrão é 100.
- Evidências exigem `dataset_id` e aceitam `verdict` igual a
  `conforme`, `violacao` ou `inconclusiva`.
- O índice do registro começa em zero após o cabeçalho. A interface soma 1 ao exibir
  o número da linha de dados; isso não é necessariamente o número físico de linha
  do arquivo quando existem células multilinha ou linhas vazias.
- Os filtros por resultado são aplicados antes da paginação.

Os nomes de coluna e valores retornados pertencem à base selecionada. O serviço não
libera registros apenas porque o navegador conhece um UUID: a propriedade da regra
e da análise é verificada.

## Conversa por SSE

O POST de mensagens mantém a conexão aberta. Os eventos são:

| Evento | Conteúdo | Ação da interface |
| --- | --- | --- |
| `delta` | JSON com text | Acrescenta o trecho à resposta temporária. |
| `done` | MessageOut com citações | Atualiza o histórico persistido. |
| `error` | JSON com message | Apresenta a falha e atualiza o histórico. |

Exemplo ilustrativo de uma resposta completa:

```text
event: delta
data: {"text":"O prazo é de 10 dias [R1]."}

event: done
data: {"id":"00000000-0000-0000-0000-000000000002","role":"assistant","content":"O prazo é de 10 dias.","citations":[{"id":"00000000-0000-0000-0000-000000000003","type":"prazo","summary":"Entregar em até 10 dias"}],"created_at":"2026-01-01T12:00:00Z"}

```

Os marcadores R1/R2 são referências temporárias daquela resposta. O backend os
relaciona aos UUIDs das regras. O texto final é devolvido sem os marcadores, com
citações separadas. A pergunta é persistida antes da chamada ao modelo, portanto uma
falha pode deixar uma pergunta no histórico sem resposta do assistente.

Uma falha SSE pode ocorrer depois do HTTP 200 inicial. Por isso o leitor do frontend
também trata o evento `error`, além de verificar o status HTTP.

## Erros e estados de domínio

O envelope de erro é:

```json
{
  "error": {
    "code": "invalid_query",
    "message": "A coluna “Data” não existe na base “contratos”."
  }
}
```

| Status HTTP | Uso comum |
| --- | --- |
| 401 | Sessão ausente, expirada ou credenciais incorretas. |
| 404 | Recurso ausente ou de outro usuário. |
| 409 | Operação incompatível com o estado: ainda processando, sem busca ou fontes alteradas. |
| 413 | Arquivo maior que o limite de entrada. |
| 422 | Conteúdo, formato, seleção ou filtro inválido. |
| 502 | Falha de armazenamento exposta pela rota. |
| 503 | IA não configurada em operações que verificam isso antes de iniciar. |

`Dataset.status = error` e `Document.status = error` são dados de domínio:
consultar esses objetos pode devolver HTTP 200. O mesmo vale para um resultado
`inconclusiva` ou `erro` na validação. Confira corpo e estado, não apenas o HTTP.

## Evoluir a API

1. Atualize os schemas Pydantic e os serviços correspondentes.
2. Atualize modelos/migrations quando a persistência mudar.
3. Ajuste a rota e os testes.
4. Gere `frontend/src/lib/api/schema.d.ts` pelo OpenAPI.
5. Adapte os hooks e componentes.
6. Atualize esta página e o fluxograma afetado.

A documentação gerada pelo FastAPI fornece os detalhes de todos os campos; os mapas
explicam por que cada endpoint existe e qual parte do produto o utiliza.
