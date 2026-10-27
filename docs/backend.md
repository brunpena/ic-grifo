# Mapa do backend

[Índice](README.md) · [Arquitetura](arquitetura.md) · [Fluxogramas](fluxos.md) · [API](api.md)

A ordem normal de uma operação é rota → serviço → modelos/Storage/provedor → contrato de saída.
Use este mapa para localizar responsabilidades sem começar pelos arquivos gerados.

## Como ler os arquivos maiores

- Em `api/v1/documents.py`, procure as seções de documentos, regras, buscas, verificação e conversa.
- Em `services/llm.py`, separe o transporte HTTP dos prompts de extração, busca e chat.
- Em `services/ingest.py`, comece pelos `start_*` e siga a função assíncrona agendada.
- Em `services/rule_validation.py`, leia `validate_document`, depois `evaluate_plan` e `records`.
- Em `services/compliance.py`, siga a compilação do critério até a avaliação de uma linha.
- Em `db/models.py`, acompanhe as relações com o diagrama da arquitetura ao lado.

## Entrada e rotas

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [app/main.py](<../backend/app/main.py>) | Monta FastAPI, CORS, logs e erros. create_app configura a aplicação; lifespan recupera tarefas interrompidas e fecha o engine. |
| [app/api/deps.py](<../backend/app/api/deps.py>) | Injeta sessões SQLAlchemy e autenticação: SessionDep, UserDep, AuthDep e OptionalAuthDep. |
| [app/api/v1/router.py](<../backend/app/api/v1/router.py>) | Agrupa health, auth, analyses e documents sob /api/v1. |
| [app/api/v1/health.py](<../backend/app/api/v1/health.py>) | Consulta SELECT 1 e informa ok/degraded e disponibilidade do banco; mantém HTTP 200 no estado degraded. |
| [app/api/v1/auth.py](<../backend/app/api/v1/auth.py>) | Cadastro, login, logout, perfil e senha. _start_session grava o hash do token e configura o cookie. |
| [app/api/v1/analyses.py](<../backend/app/api/v1/analyses.py>) | CRUD de análises, upload e remoção de CSVs. owned_analysis verifica o dono; upload_dataset salva e agenda a leitura. |
| [app/api/v1/documents.py](<../backend/app/api/v1/documents.py>) | Documentos, PDF, regras, buscas, validação e chat. Comece em _create_document, _rules_out, validate_document e send_message. |

## Configuração, segurança e persistência

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [app/core/config.py](<../backend/app/core/config.py>) | Settings lê ambiente e .env, normaliza URLs e limites; get_settings mantém a configuração em cache. |
| [app/core/security.py](<../backend/app/core/security.py>) | Hashes scrypt das senhas, tokens aleatórios e hash SHA-256 dos tokens de sessão. |
| [app/core/errors.py](<../backend/app/core/errors.py>) | AppError e subclasses; handlers padronizam respostas error.code e error.message em português. |
| [app/core/json.py](<../backend/app/core/json.py>) | Serialização com orjson e classe OrjsonResponse utilizada em erros. |
| [app/core/logging.py](<../backend/app/core/logging.py>) | Logs JSON, mascaramento de campos extras sensíveis e log_step para medir duração das etapas. |
| [app/db/models.py](<../backend/app/db/models.py>) | Tabelas, relações, restrições e índices. Define estados, metadados das bases e Rule.validation. |
| [app/db/session.py](<../backend/app/db/session.py>) | Engine asyncpg, configuração de pooler, SessionLocal e sessão por requisição em get_session. |

## Contratos Pydantic

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [app/schemas/analyses.py](<../backend/app/schemas/analyses.py>) | Entradas/saídas de análises e bases, tipos das colunas e sua interpretação semantic. |
| [app/schemas/auth.py](<../backend/app/schemas/auth.py>) | Valida cadastro, login, perfil e senha; normaliza e-mail e define os dados públicos do usuário. |
| [app/schemas/common.py](<../backend/app/schemas/common.py>) | Envelope dos erros e função error_responses para documentar respostas de falha. |
| [app/schemas/documents.py](<../backend/app/schemas/documents.py>) | DocumentOut, RuleOut, retângulos, texto/link, regras manuais e mensagens com citações. |
| [app/schemas/queries.py](<../backend/app/schemas/queries.py>) | StructuredQuery, condições, grupos, operadores e registros encontrados; limites de condições e profundidade. |
| [app/schemas/validation.py](<../backend/app/schemas/validation.py>) | ColumnMeaning, Operand, ComplianceCheck, DatasetCheck, ValidationPlan, contagens e evidências por registro. |

## Serviços e motores

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [app/services/ingest.py](<../backend/app/services/ingest.py>) | Coordena tarefas asyncio, processamento dos CSVs e documentos, pedidos concorrentes de validação e recuperação na inicialização. |
| [app/services/datasets.py](<../backend/app/services/datasets.py>) | parse_csv detecta codificação/separador; infer_column identifica tipos; parse_value converte células. Também nomeia e limita arquivos. |
| [app/services/storage.py](<../backend/app/services/storage.py>) | Salva, lê e remove PDFs/CSVs em disco ou Supabase Storage; considera limite do bucket e envia corpos em blocos. |
| [app/services/safe_fetch.py](<../backend/app/services/safe_fetch.py>) | Download HTTP/HTTPS com limite de tempo/tamanho; bloqueia IPs privados, fixa a resolução e revalida redirecionamentos. |
| [app/services/pdf_text.py](<../backend/app/services/pdf_text.py>) | Extrai páginas, palavras, posições e full_text com PyMuPDF. Recusa PDFs ilegíveis ou sem texto. |
| [app/services/text_match.py](<../backend/app/services/text_match.py>) | find_excerpt localiza texto selecionado tolerando espaços e travessões; usado por regras manuais. |
| [app/services/highlights.py](<../backend/app/services/highlights.py>) | rule_boxes transforma intervalos de texto em retângulos normalizados; page_range localiza o texto da página. |
| [app/services/llm.py](<../backend/app/services/llm.py>) | Transporte Gemini REST, retries e reforço de requisição lenta; extração em blocos, geração de buscas e chat por streaming. |
| [app/services/validation_llm.py](<../backend/app/services/validation_llm.py>) | interpret_columns propõe significados sem mudar tipos físicos; plan_rules propõe e valida planos de conformidade por regra e lote. |
| [app/services/query_engine.py](<../backend/app/services/query_engine.py>) | Compila filtros seguros, normaliza valores, carrega linhas tipadas e executa seleção. Mantém cache de quatro bases. |
| [app/services/rule_queries.py](<../backend/app/services/rule_queries.py>) | Gera e executa buscas, grava contagens/índices e preserva buscas manuais. analysis_datasets retorna apenas bases prontas. |
| [app/services/compliance.py](<../backend/app/services/compliance.py>) | Motor sem banco: compile_check/compile_validation validam critérios; evaluate_rows calcula evidências; summarize agrega a regra. |
| [app/services/rule_validation.py](<../backend/app/services/rule_validation.py>) | Coordena significados, planos e resultados. validate_document avalia todas as regras; source_signature confere fontes; records reproduz evidências. |

## Conversores

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [app/services/converters/base.py](<../backend/app/services/converters/base.py>) | Contrato SourceFile → ConvertedDocument, classe Converter e erros de conversão. A saída contém PDF e ExtractedDocument. |
| [app/services/converters/registry.py](<../backend/app/services/converters/registry.py>) | Registra PDF/HTML/TXT e escolhe por MIME type, extensão e conteúdo. |
| [app/services/converters/pdf.py](<../backend/app/services/converters/pdf.py>) | Valida PDF e extrai texto/posições preservando o arquivo original. |
| [app/services/converters/html.py](<../backend/app/services/converters/html.py>) | Decodifica e limpa HTML, prepara tabelas, gera PDF e o relê para obter coordenadas. |
| [app/services/converters/text.py](<../backend/app/services/converters/text.py>) | Decodifica TXT, escapa conteúdo, preserva parágrafos e escolhe título antes da diagramação. |
| [app/services/converters/render.py](<../backend/app/services/converters/render.py>) | html_to_pdf diagrama HTML limpo em A4 com Story/DocumentWriter do PyMuPDF. |
| [app/services/converters/__init__.py](<../backend/app/services/converters/__init__.py>) | Reexporta contratos, erros e registro dos conversores para as demais camadas. |

## Migrations

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [alembic.ini](<../backend/alembic.ini>) | Caminhos e logging do Alembic; a URL efetiva é obtida das configurações da aplicação. |
| [migrations/env.py](<../backend/migrations/env.py>) | Integra Settings, engine assíncrono e Base.metadata ao Alembic; permite modo online e offline. |
| [migrations/script.py.mako](<../backend/migrations/script.py.mako>) | Template para novas migrations. |
| [migrations/README](<../backend/migrations/README>) | Identifica o diretório de migrations. |
| [migrations/versions/0001_initial.py](<../backend/migrations/versions/0001_initial.py>) | Cria documentos, páginas, palavras, regras, conversas e mensagens, incluindo estrutura vetorial. |
| [migrations/versions/0002_users.py](<../backend/migrations/versions/0002_users.py>) | Cria usuários e sessões. |
| [migrations/versions/0003_document_owner.py](<../backend/migrations/versions/0003_document_owner.py>) | Adiciona o proprietário dos documentos. |
| [migrations/versions/0004_analyses_datasets.py](<../backend/migrations/versions/0004_analyses_datasets.py>) | Introduz análises, CSVs e buscas; associa documentos à análise. |
| [migrations/versions/0005_rule_datasets.py](<../backend/migrations/versions/0005_rule_datasets.py>) | Relaciona regras às bases identificadas na extração. |
| [migrations/versions/0006_dataset_status.py](<../backend/migrations/versions/0006_dataset_status.py>) | Adiciona estado/mensagem da leitura das bases e remove sample_rows do banco. |
| [migrations/versions/0007_rule_validation.py](<../backend/migrations/versions/0007_rule_validation.py>) | Adiciona o tamanho original dos CSVs e o JSONB de validação das regras. |

## Testes

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [tests/conftest.py](<../backend/tests/conftest.py>) | Ambiente e cliente HTTP de testes; verifica o banco, pula testes db indisponíveis e recria seu esquema em migrated_db. |
| [tests/test_app.py](<../backend/tests/test_app.py>) | Configuração, CORS, erros, OpenAPI, health e migrations. |
| [tests/test_auth.py](<../backend/tests/test_auth.py>) | Hashes, cadastro/login/logout, perfil, senha e encerramento de outras sessões. |
| [tests/test_datasets.py](<../backend/tests/test_datasets.py>) | CSV, tipos, nomes, limites e fluxo assíncrono de análises e bases. |
| [tests/test_converters.py](<../backend/tests/test_converters.py>) | Formatos, limpeza de HTML, texto, PDFs sem conteúdo e tabelas entre páginas. |
| [tests/test_documents.py](<../backend/tests/test_documents.py>) | Extração, intervalos, deduplicação, grifos, regras manuais, privacidade e conversa; simula a IA. |
| [tests/test_llm.py](<../backend/tests/test_llm.py>) | Gemini simulado: extração, retries, quota, streaming, requisição de reforço e cancelamento. |
| [tests/test_safe_fetch.py](<../backend/tests/test_safe_fetch.py>) | Rede simulada: endereços privados, DNS, redirecionamentos e limites de download. |
| [tests/test_queries.py](<../backend/tests/test_queries.py>) | Operadores, normalização, erros e fluxo regra → busca → registros com IA simulada. |
| [tests/test_compliance.py](<../backend/tests/test_compliance.py>) | Prazos, percentuais, dados ausentes, lógica de três valores, paginação, planos e versões das fontes. |
| [tests/test_validation_api.py](<../backend/tests/test_validation_api.py>) | Fluxo com banco e IA simulada: cobertura das regras, evidências, permissões, remoção e concorrência. |

## Execução e apoio

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [.dockerignore](<../backend/.dockerignore>) | Exclui arquivos locais e desnecessários do contexto da imagem. |
| [.env.example](<../backend/.env.example>) | Modelo público de configuração, sem a chave real de execução. |
| [.gitignore](<../backend/.gitignore>) | Exclui ambiente virtual, segredos locais, dados, bytecode e caches. |
| [.python-version](<../backend/.python-version>) | Seleciona Python 3.12 para ferramentas compatíveis. |
| [pyproject.toml](<../backend/pyproject.toml>) | Dependências Python, requisitos de versão, pytest e Ruff. |
| [uv.lock](<../backend/uv.lock>) | Resolução travada de dependências gerada pelo uv. |
| [Dockerfile](<../backend/Dockerfile>) | Build em estágios, ambiente virtual, usuário app, healthcheck e entrypoint. |
| [docker-compose.dev.yml](<../backend/docker-compose.dev.yml>) | PostgreSQL/pgvector local na porta 54329, volume e inicialização do banco de testes. |
| [docker-compose.yml](<../backend/docker-compose.yml>) | API para deploy com banco e arquivos externos; ainda contém nomes antigos de configuração da IA. |
| [docker-entrypoint.sh](<../backend/docker-entrypoint.sh>) | Aplica migrations e inicia Uvicorn em um processo. |
| [scripts/init-test-db.sql](<../backend/scripts/init-test-db.sql>) | Cria icgrifo_test na primeira inicialização do volume PostgreSQL. |
| [scripts/bench_extraction.py](<../backend/scripts/bench_extraction.py>) | Mede tempo e tokens de extração de um documento existente; chama a IA real e não grava os resultados no banco. |
| [README.md](<../backend/README.md>) | Comandos e navegação da documentação do servidor. |
| [VALIDACAO.md](<../backend/VALIDACAO.md>) | Resumo operacional da verificação de cumprimento. |

## Marcadores de pacotes Python

Estes arquivos delimitam os pacotes importáveis. Não iniciam rotas ou tarefas por si só.

| Arquivo | Papel |
| --- | --- |
| [app/__init__.py](<../backend/app/__init__.py>) | Marcador do pacote Python correspondente. |
| [app/api/__init__.py](<../backend/app/api/__init__.py>) | Marcador do pacote Python correspondente. |
| [app/api/v1/__init__.py](<../backend/app/api/v1/__init__.py>) | Marcador do pacote Python correspondente. |
| [app/core/__init__.py](<../backend/app/core/__init__.py>) | Marcador do pacote Python correspondente. |
| [app/db/__init__.py](<../backend/app/db/__init__.py>) | Marcador do pacote Python correspondente. |
| [app/schemas/__init__.py](<../backend/app/schemas/__init__.py>) | Marcador do pacote Python correspondente. |
| [app/services/__init__.py](<../backend/app/services/__init__.py>) | Marcador do pacote Python correspondente. |
| [tests/__init__.py](<../backend/tests/__init__.py>) | Marcador do pacote Python correspondente. |

## Pontes entre camadas

| Operação | Entrada | Serviço | Saída |
| --- | --- | --- | --- |
| CSV | analyses.upload_dataset | ingest.process_dataset | DatasetOut |
| Documento | documents._create_document | conversores e ingest.process_document | DocumentOut |
| Grifos | documents.list_rules | highlights.rule_boxes | RuleOut |
| Buscas | documents.generate_document_queries | rule_queries.generate_for_document | RuleOut após processamento |
| Cumprimento | documents.validate_document | rule_validation.validate_document | RuleValidationOut em RuleOut |
| Evidência | documents.validation_records | rule_validation.records | ValidationRecordsOut |
| Conversa | documents.send_message | llm.stream_chat | SSE e MessageOut |
