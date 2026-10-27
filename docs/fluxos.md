# Fluxos do sistema

[Índice](README.md) · [Arquitetura](arquitetura.md) · [API](api.md)

Cada diagrama mostra uma operação. Os nomes em código na explicação são os pontos
para abrir no editor. Respostas 202 indicam que uma tarefa continua após a requisição.

## 1. Entrada e autenticação

```mermaid
sequenceDiagram
    actor Pessoa
    participant Tela as Next.js / AppShell
    participant Hook as auth.ts
    participant API as auth.py / deps.py
    participant DB as PostgreSQL
    Pessoa->>Tela: Abre o sistema
    Tela->>Hook: useCurrentUser
    Hook->>API: GET /api/v1/auth/me com cookie
    API->>DB: Procura hash de token e validade
    alt Sessão válida
        DB-->>API: Usuário da sessão
        API-->>Tela: Dados do usuário
    else Sem sessão válida
        API-->>Tela: 401
        Tela-->>Pessoa: Redireciona para /login
        Pessoa->>Tela: Informa e-mail e senha
        Tela->>API: POST /api/v1/auth/login
        API->>DB: Verifica usuário e grava sessão
        API-->>Tela: Usuário e cookie httpOnly
    end
```

O cadastro também inicia uma sessão. O logout remove a sessão atual e limpa o cookie.
A troca de senha encerra outras sessões. A proteção dos recursos acontece em
[deps.py](../backend/app/api/deps.py) e nas funções `owned_analysis`,
`_owned_document` e `_owned_rule`, além do redirecionamento visual de `AppShell`.

## 2. Envio de CSV e interpretação das colunas

```mermaid
flowchart TD
    A["DatasetUploader seleciona um ou vários arquivos"] --> B["ensureAnalysis cria ou reutiliza a análise"]
    B --> C["POST multipart com progresso de bytes"]
    C --> D["upload_dataset verifica formato, tamanho e armazenamento"]
    D --> E["Salva o CSV e Dataset em processing"]
    E --> F["Retorna 202"]
    E --> G["process_dataset lê o arquivo"]
    G --> H["parse_csv detecta codificação, separador e tipos"]
    H --> I["interpret_columns propõe significado, evento, unidade e confiança"]
    I --> J["Grava metadados e marca ready"]
    H --> K["CSV inválido: marca error"]
    I --> L["Falha da IA: mantém leitura com significado não confirmado"]
    L --> J
    J --> M["Invalida resultados e solicita validação dos documentos"]
    F --> N["useAnalysis consulta a cada 1,5 s enquanto houver base em processing"]
```

O progresso do envio não é o progresso da leitura no servidor.
[client.ts](../frontend/src/lib/api/client.ts) usa XMLHttpRequest para medir os bytes;
[analyses.ts](../frontend/src/lib/analyses.ts) acompanha o processamento por consultas.

O caminho do backend é `upload_dataset` →
`storage.save_file` → `ingest.start_dataset_processing` →
`process_dataset` → `rule_validation.interpret`.

O CSV pode ser cortado na última quebra de linha que cabe no limite do armazenamento.
O tamanho original é preservado para identificar essa cobertura parcial. A presença
de uma coluna semanticamente ambígua não torna o CSV ilegível, mas impede conclusões
que dependam dela.

## 3. Entrada e processamento de documentos

```mermaid
flowchart TD
    A["Arquivo PDF, HTML ou TXT"] --> D["_create_document"]
    B["Texto colado"] --> D
    C["Link HTTP ou HTTPS"] --> S["safe_fetch: valida endereço e baixa conteúdo"]
    S --> D
    D --> R["ConverterRegistry escolhe o conversor"]
    R --> P["PDF: lê texto e posições"]
    R --> H["HTML ou TXT: limpa, diagrama e lê o PDF gerado"]
    P --> G["Salva PDF e Document em processing"]
    H --> G
    G --> RESP["Retorna 202"]
    G --> T["process_document grava texto, páginas e palavras"]
    T --> E["Marca extracting_rules"]
    E --> L["Gemini extrai regras de blocos com frases numeradas"]
    L --> U["Deduplica e grava Rule"]
    U --> Q["Com bases prontas: gera buscas relacionadas"]
    Q --> V["Verifica todas as regras nas bases"]
    U --> N["Sem bases: registra resultados inconclusivos"]
    V --> OK["Document ready"]
    N --> OK
    T --> ER["Falha de leitura ou extração: Document error"]
```

A conversão acontece antes de devolver 202. A extração de regras e as etapas seguintes
continuam em segundo plano. Um PDF sem texto é recusado: o projeto não executa OCR.

Arquivos centrais:
[documents.py](../backend/app/api/v1/documents.py),
[registry.py](../backend/app/services/converters/registry.py),
[pdf_text.py](../backend/app/services/pdf_text.py),
[ingest.py](../backend/app/services/ingest.py) e
[llm.py](../backend/app/services/llm.py).

Os blocos de texto têm sobreposição para não perder regras na fronteira.
A IA devolve números de frases; o backend encontra os intervalos exatos no texto.
O chat e as tabelas passam a usar as regras persistidas.

## 4. Como o grifo aparece na página

```mermaid
flowchart LR
    P["Palavras extraídas do PDF"] --> W["Word: intervalo de texto e coordenadas"]
    R["Rule: início e fim do trecho"] --> H["rule_boxes encontra palavras sobrepostas"]
    W --> H
    H --> B["Une palavras vizinhas em retângulos"]
    B --> F["Normaliza posições por largura e altura da página"]
    F --> O["RuleOut.boxes"]
    O --> UI["HighlightLayer desenha sobre o PDF"]
```

O visualizador usa pdf.js para desenhar páginas e sua camada de texto. O backend usa
PyMuPDF para extrair palavras. Como os grifos são frações da página, continuam ligados
ao trecho ao mudar o zoom.

Na criação manual, o navegador envia página, trecho e resumo. `create_rule` usa
`page_range` e `find_excerpt` para localizar o texto no servidor; não aceita apenas
um retângulo visual como prova da existência de uma regra.

## 5. Busca de registros e validação de cumprimento

```mermaid
flowchart LR
    R["Regra"] --> Q["Filtro de busca StructuredQuery"]
    Q --> CQ["compile_query"]
    CQ --> LIN["Índices de linhas relacionadas"]
    LIN --> BUSCA["RuleQuery: contagem e registros encontrados"]
    R --> PL["ValidationPlan: escopo e critérios"]
    PL --> CV["compile_validation"]
    CV --> EV["evaluate_rows"]
    EV --> RES["Conforme, violação ou inconclusiva por registro"]
    RES --> SOMA["summarize: resultado da regra"]
    SOMA --> JSON["Rule.validation"]
```

A busca responde **quais registros estão relacionados**. A validação responde
**se esses registros cumprem a regra**. Uma busca que executou com `state = ok`
não comprova conformidade.

A geração automática inicial de buscas considera as regras ligadas a bases na
extração. O comando manual de gerar buscas pode considerar as demais regras não
rejeitadas. Buscas manuais são preservadas.

A validação considera todas as regras extraídas; regras rejeitadas são registradas
como ignoradas. Regras sem dados verificáveis recebem um resultado explicativo.
O [exemplo completo](validacao.md) mostra os dois caminhos para a mesma obrigação.

## 6. Revalidar, alterar bases e carregar evidências

```mermaid
sequenceDiagram
    participant Tela as Assistente
    participant API as documents.py
    participant Tarefa as ingest.py
    participant Servico as rule_validation.py
    participant Motor as compliance.py
    participant DB as PostgreSQL
    Tela->>API: POST /documents/id/validation
    API->>DB: Reserva Document ready para extracting_rules
    API-->>Tela: 202
    Tarefa->>Servico: validate_document
    Servico->>DB: Carrega regras e bases prontas
    Servico->>Servico: Interpreta colunas quando necessário
    Servico->>Servico: Pede planos para todas as regras ativas
    Servico->>Motor: Compila e avalia linhas
    Motor-->>Servico: Contagens e critérios
    Servico->>DB: Persiste resultado, plano e assinatura das fontes
    Tarefa->>DB: Document ready
    Tela->>API: Consulta status e regras
    Tela->>API: GET /rules/id/validation/records
    API->>Servico: Confere fontes e reproduz o plano
    Servico-->>Tela: Página de registros com evidências
```

Os prefixos omitidos apenas nos rótulos desse diagrama são `/api/v1`.
As fontes são verificadas novamente antes de servir evidências. Base removida ou
significado alterado exige nova verificação.

Se uma base termina de carregar enquanto outra avaliação está em execução,
`_validation_requested` registra um pedido pendente. Ao terminar, o documento
pode iniciar outra rodada com as fontes atualizadas.

## 7. Conversa com resposta em streaming

```mermaid
sequenceDiagram
    actor Pessoa
    participant UI as AssistantView
    participant API as documents.send_message
    participant IA as llm.stream_chat
    participant DB as PostgreSQL
    Pessoa->>UI: Faz uma pergunta
    UI->>API: POST /documents/id/messages
    API->>DB: Salva pergunta e carrega até 20 mensagens anteriores
    API->>IA: Documento paginado, regras não rejeitadas e histórico
    loop Pedaços de resposta
        IA-->>API: Texto
        API-->>UI: Evento delta
    end
    API->>DB: Salva resposta e IDs das regras citadas
    API-->>UI: Evento done com mensagem e citações
    UI->>UI: Atualiza histórico e chips clicáveis
```

Esse chat usa o documento aberto. Não executa uma busca semântica global nem recebe
automaticamente todas as linhas dos CSVs ou o relatório completo de conformidade.
Falhas podem chegar por evento `error` depois que a conexão SSE já foi aberta.

## 8. Reinício da API

```mermaid
flowchart TD
    A["lifespan inicia"] --> B["recover_interrupted"]
    B --> C["Bases em processing: agenda nova leitura do arquivo"]
    B --> D["Documentos em extracting_rules: limpa validações interrompidas"]
    D --> E{"O documento já tem regras?"}
    E -->|Sim| F["Marca ready com aviso de interrupção"]
    E -->|Não| G["Marca error e orienta reenviar"]
    B --> H["Documentos ainda em processing: marca error"]
    C --> I["Processamento normal da base"]
```

A recuperação não representa uma fila durável de tarefas. Ela usa os estados
persistidos para decidir o que pode ser retomado e o que exige uma nova ação.
