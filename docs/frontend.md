# Mapa do frontend

[Índice](README.md) · [Arquitetura](arquitetura.md) · [Fluxos](fluxos.md)

As rotas ficam em `src/app`; os componentes em `src/components`; os hooks e o cliente
da API em `src/lib`. O alias `@/` aponta para `src/`.

## Árvore de composição principal

```mermaid
flowchart TD
    L["RootLayout"] --> P["Providers"]
    P --> APP["Layout do grupo app"]
    APP --> SHELL["AppShell"]
    SHELL --> AS["AssistantView"]
    SHELL --> KB["KnowledgeBaseView: demonstração"]
    SHELL --> SET["SettingsView"]
    AS --> WORK["AnalysisWorkspace no desktop"]
    WORK --> CHAT["Conversa"]
    WORK --> PDF["Documento e grifos"]
    WORK --> RULES["Regras e resumo de validação"]
    WORK --> REC["Registros e evidências"]
```

No celular, o Assistente usa abas em vez dos painéis redimensionáveis.

## Estado, consultas e atualização

| Informação | Dono principal | Exemplo |
| --- | --- | --- |
| Dados da API | TanStack Query em `lib/` | Regras e análise. |
| Interação temporária | Estado de `AssistantView` | Seleção, filtros, pergunta e aba móvel. |
| Streaming | Estado temporário e depois histórico da API | Pedaços de resposta até o evento final. |
| Preferências | Hooks de persistência e tema | Painéis, larguras e aparência. |
| Grifo | Coordenadas da API renderizadas na interface | O navegador desenha as marcações. |

`useAnalysis` consulta a cada 1,5 segundo enquanto há base em processamento.
`useDocument` consulta a cada 1,5 segundo só enquanto o documento está em processamento;
pronto ou com erro, para. Quando uma base termina de ser lida, o servidor volta a preparar
as buscas dos documentos prontos: `useAnalysis` percebe essa transição, recarrega o
documento e o acompanha por 10 segundos. Ações como gerar buscas ou validar devolvem o
documento já em andamento, e a consulta recomeça sozinha.

`useRules`, `useRuleRecords` e `useValidationRecords` não fazem consultas periódicas.
A transição do documento para pronto (não a abertura de um documento já pronto) invalida
regras, registros, evidências e análise; remover uma base também invalida esses caches.
Registros e evidências ficam 5 minutos em cache, então voltar a uma regra já vista não
consulta o DuckDB de novo. Ao reabrir pelo histórico, o documento da lista entra no
cache (`seedDocument`), e PDF, regras e situação atual carregam em paralelo.

O último usuário logado fica em `localStorage` (`grifo:user`). Logo após a hidratação,
`seedStoredUser` o coloca no cache como desatualizado: menu, cabeçalho e as consultas da
página começam sem esperar `/auth/me`, que confere a sessão em paralelo. Um 401 apaga a
cópia e o AppShell manda para o login; login e cadastro só redirecionam com o usuário
confirmado pela API (`dataUpdatedAt > 0`). O PDF de cada documento volta com
`Cache-Control: private, immutable`, então o navegador o reaproveita ao recarregar a página.

A tela de entrada não carrega o espaço de trabalho: `AnalysisWorkspace`, `RulesTable`,
`RecordsPanel`, `QueryEditorDialog` e `CreateRulePopover` usam `next/dynamic` e são
pré-carregados assim que existe uma análise (`preloadWorkspace`).

O envio de CSV usa XMLHttpRequest para medir bytes. O chat usa fetch e leitura de SSE
porque a operação precisa de POST. Consultas comuns usam o cliente OpenAPI tipado.

## Idiomas (português e inglês)

A interface tem português e inglês. As bandeiras (`LanguageToggle`) ficam no cabeçalho e
nas telas de login/cadastro; em Configurações há a mesma escolha por extenso.

O idioma faz parte da URL: todas as páginas ficam em `src/app/[lang]` (`/pt/assistente`,
`/en/assistente`). O layout raiz valida o `[lang]` (outro valor dá 404), define
`<html lang>` e entrega o idioma por contexto (`LocaleProvider`); `useLocale()` lê esse
contexto. Por isso o servidor já renderiza no idioma certo e cada idioma tem o seu link.

- **Trocar de idioma** (`useSetLocale`) vai para o mesmo caminho e query com o outro
  prefixo, com `replace` (o Voltar do navegador não alterna idiomas), e grava o cookie
  `grifo-locale`.
- **Links sem idioma** (favoritos antigos, `/`): o [proxy](<../frontend/src/proxy.ts>)
  redireciona para o idioma do cookie ou, na primeira visita, do `Accept-Language`.
- **Links internos** usam `useLocalePath()`: `href("/regras")` → `/en/regras`. O menu
  (`nav.ts`) guarda os caminhos sem idioma, e `navItemFor` aceita os dois formatos. O
  `?next=` do login guarda o caminho sem idioma, completado na volta.
- **Títulos da aba** são traduzidos no servidor com `localizedMetadata(msg("…"))`
  ([metadata.ts](<../frontend/src/lib/i18n/metadata.ts>)), que lê o idioma com
  `next/root-params`. Código de servidor importa de `@/lib/i18n/core` (sem hooks).

- **Como traduzir um texto:** em componentes, `const t = useT()` e `t("Texto em português")`.
  O texto em português é a própria chave; a versão em inglês fica em
  [src/lib/i18n/en.ts](<../frontend/src/lib/i18n/en.ts>). Sem tradução, aparece em português.
- **Variáveis e plural:** `t("Remover {name}", { name })`, `t.plural(n, "{n} linha", "{n} linhas")`;
  números com `t.number(n)` e datas com `intlLocale(t.locale)`.
- **Constantes fora de componentes** (rótulos de tipos, operadores, menus): marque com
  `msg("…")` e traduza ao exibir com `t(valor)`.
- **Funções que montam texto** recebem `t` como argumento (`describeQuery(query, t)`,
  `errorMessage(error, t)`): o React Compiler memoriza resultados pelos argumentos, e o
  idioma precisa ser um deles para o texto mudar ao trocar de idioma.
- **Conferência:** `npm run i18n:check` lista textos sem tradução, variáveis diferentes e
  traduções sem uso.
- **Hidratação:** o HTML pré-renderizado já está no idioma da URL. O AppShell só mostra o
  usuário guardado no navegador depois de `useHydrated()`, para o HTML coincidir.

Continuam em português: mensagens do servidor montadas com valores ou não listadas em
[server-messages.ts](<../frontend/src/lib/api/server-messages.ts>), o que a IA gera (resumos
das regras, interpretações, explicações), os dados de exemplo da Base de regras e a
vitrine `/dev/ui`.

## Etapas do Assistente na URL

Cada etapa tem o seu endereço, então Voltar/Avançar, recarregar e compartilhar funcionam:

| URL | Tela |
| --- | --- |
| `/{lang}/assistente` | Nova análise: envio das bases e histórico. |
| `/{lang}/assistente/analises/{id}` | Análise com as bases, esperando o documento. |
| `/{lang}/assistente/documentos/{id}` | Documento aberto no espaço de trabalho; a análise vem do documento. |

`AssistantView` fica no [layout de /assistente](<../frontend/src/app/[lang]/(app)/assistente/layout.tsx>),
e as páginas de cada etapa não renderizam nada: trocar de etapa muda só a URL, sem
desmontar a tela (envios em andamento e o PDF aberto continuam). Os ids saem de
[assistant-route.ts](<../frontend/src/components/assistant/assistant-route.ts>):
`useAssistantRoute` lê a URL e `navigate` empilha a etapa no histórico (até a URL mudar,
a tela já usa o destino, sem piscar a etapa anterior). A primeira base cria a análise e
vai para `analises/{id}`; o documento enviado abre `documentos/{id}`; o histórico e
"Nova análise" também navegam. Um id inexistente (ou de outra conta) mostra um aviso com
o botão "Nova análise".

`useAnalysisLifecycle` encerra a análise (`POST /analyses/{id}/close`) quando outra
análise entra no lugar, ao sair do Assistente ou ao fechar a aba. Voltar para a tela
inicial não encerra, e trocar de idioma (que recarrega a página) também não.

As páginas com id só são conhecidas no pedido; com `cacheComponents`, o AppShell fica em
`<Suspense>` e o HTML pré-renderizado delas é o skeleton da estrutura.

## Conexão com a API

- O layout raiz inclui `<link rel="preconnect">` para `NEXT_PUBLIC_API_URL`: DNS, TCP e TLS
  com a API começam enquanto o JavaScript carrega.
- A API devolve `Access-Control-Max-Age` (`CORS_MAX_AGE_SECONDS`): o navegador guarda o
  preflight em vez de repeti-lo antes de cada POST/PATCH/DELETE.
- Respostas JSON grandes saem com gzip (`GZIP_MIN_BYTES`); PDFs e o SSE do chat não.
- No Docker, o uvicorn mantém a conexão aberta por 75 s (`UVICORN_KEEP_ALIVE`; o padrão
  dele é 5 s), evitando um novo handshake entre as ações da pessoa.

## Roteiro dentro de AssistantView

1. `ensureAnalysis`, `openFiles` e `openDocument`: criação e seleção do contexto.
2. Hooks `useAnalysis`, `useDocument`, `useRules` e `useMessages`: dados remotos.
3. `send`: pergunta e resposta temporária.
4. `goToRule`, seleção e pesquisa: sincronização de documento e tabelas.
5. `chatPanel`, `documentPanel`, `rulesPanel` e `tablePanel`: composição das áreas.
6. Diálogos finais: bases, editor de busca e criação manual de regra.

## Rotas e composição

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [src/proxy.ts](<../frontend/src/proxy.ts>) | Redireciona caminhos sem idioma para `/pt/...` ou `/en/...` (cookie ou navegador). |
| [src/app/[lang]/layout.tsx](<../frontend/src/app/[lang]/layout.tsx>) | Layout raiz: valida o idioma, `<html lang>`, Geist, metadados, preconnect da API, tema inicial, LocaleProvider e Providers. |
| [src/app/[lang]/providers.tsx](<../frontend/src/app/[lang]/providers.tsx>) | Disponibiliza QueryClient e ToastProvider; configura cache, tentativas e comportamento de foco. |
| [src/app/[lang]/page.tsx](<../frontend/src/app/[lang]/page.tsx>) | Redireciona /{lang} para /{lang}/assistente. |
| [src/app/globals.css](<../frontend/src/app/globals.css>) | Estilos globais, tokens, temas e integração Tailwind. |
| [src/app/[lang]/(app)/layout.tsx](<../frontend/src/app/[lang]/(app)/layout.tsx>) | Envolve as telas principais em AppShell (dentro de Suspense); o grupo entre parênteses não faz parte da URL. |
| [src/app/[lang]/(app)/assistente/layout.tsx](<../frontend/src/app/[lang]/(app)/assistente/layout.tsx>) | Monta AssistantView uma vez para todas as etapas do Assistente (`/assistente`, `analises/[analysisId]`, `documentos/[documentId]`); as páginas de cada etapa só têm metadados. |
| [src/app/[lang]/(app)/regras/page.tsx](<../frontend/src/app/[lang]/(app)/regras/page.tsx>) | Rota /regras com KnowledgeBaseView demonstrativa. |
| [src/app/[lang]/(app)/configuracoes/page.tsx](<../frontend/src/app/[lang]/(app)/configuracoes/page.tsx>) | Rota /configuracoes com SettingsView. |
| [src/app/[lang]/(app)/desempenho/page.tsx](<../frontend/src/app/[lang]/(app)/desempenho/page.tsx>) | Rota /desempenho com PerformanceView. |
| [src/app/[lang]/(auth)/layout.tsx](<../frontend/src/app/[lang]/(auth)/layout.tsx>) | Composição visual das telas de login/cadastro e controle de tema. |
| [src/app/[lang]/(auth)/login/page.tsx](<../frontend/src/app/[lang]/(auth)/login/page.tsx>) | Monta o formulário de login. |
| [src/app/[lang]/(auth)/cadastro/page.tsx](<../frontend/src/app/[lang]/(auth)/cadastro/page.tsx>) | Monta o formulário de cadastro. |
| [src/app/[lang]/dev/ui/page.tsx](<../frontend/src/app/[lang]/dev/ui/page.tsx>) | Entrada da galeria /dev/ui. |
| [src/app/[lang]/dev/ui/ui-demo.tsx](<../frontend/src/app/[lang]/dev/ui/ui-demo.tsx>) | Galeria visual de componentes; usa SystemDemo. |
| [src/app/[lang]/dev/ui/system-demo.tsx](<../frontend/src/app/[lang]/dev/ui/system-demo.tsx>) | Demonstrações locais de telas, conversa, envio e estados; não executa o processamento real. |
| [src/app/opengraph-image.tsx](<../frontend/src/app/opengraph-image.tsx>) | Gera imagem de compartilhamento usando logo e fontes locais. |

## Estrutura, autenticação e configurações

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [src/components/app/app-shell.tsx](<../frontend/src/components/app/app-shell.tsx>) | Consulta a sessão, redireciona ao login e organiza sidebar, cabeçalho e navegação móvel. |
| [src/components/app/app-header.tsx](<../frontend/src/components/app/app-header.tsx>) | Cabeçalho da seção e controles de navegação/tema. |
| [src/components/app/app-sidebar.tsx](<../frontend/src/components/app/app-sidebar.tsx>) | Navegação, usuário, configurações e saída. |
| [src/components/app/nav.ts](<../frontend/src/components/app/nav.ts>) | Rotas, rótulos e identificação da seção atual. |
| [src/components/app/use-sign-out.ts](<../frontend/src/components/app/use-sign-out.ts>) | Coordena logout e navegação. |
| [src/components/auth/login-form.tsx](<../frontend/src/components/auth/login-form.tsx>) | Login, erros e redirecionamento next; reconhece sessão existente. |
| [src/components/auth/register-form.tsx](<../frontend/src/components/auth/register-form.tsx>) | Cadastro, validação de formulário, erros e navegação após criar a conta. |
| [src/components/settings/settings-view.tsx](<../frontend/src/components/settings/settings-view.tsx>) | Perfil/senha via API, aparência, sessão e status do servidor. |
| [src/components/performance/performance-view.tsx](<../frontend/src/components/performance/performance-view.tsx>) | Página de desempenho: indicadores, linha do tempo, tempo por categoria, tabela ordenável por rota e detalhe com chamadas lentas e sugestões. |
| [src/components/performance/simulation-panel.tsx](<../frontend/src/components/performance/simulation-panel.tsx>) | Formulário e resultado das simulações (quem chamou × servidor, histograma) e histórico. |
| [src/components/performance/charts.tsx](<../frontend/src/components/performance/charts.tsx>) | Gráfico de média/p95 no tempo e histograma de durações, em SVG/HTML sem bibliotecas. |
| [src/components/performance/format.ts](<../frontend/src/components/performance/format.ts>) | Formatação de milissegundos, contagens e bytes no idioma atual. |
| [src/components/api-status.tsx](<../frontend/src/components/api-status.tsx>) | Consulta health e apresenta a disponibilidade da API/banco. |
| [src/components/brand-logo.tsx](<../frontend/src/components/brand-logo.tsx>) | Identidade visual reutilizável. |
| [src/components/theme-toggle.tsx](<../frontend/src/components/theme-toggle.tsx>) | Controle de alternância do tema. |

## Assistente, envio e conversa

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [src/components/assistant/assistant-view.tsx](<../frontend/src/components/assistant/assistant-view.tsx>) | Coordena a tela real: análise/documento, envio, conversa, seleção, PDF, filtros, painéis e validação. |
| [src/components/assistant/assistant-composer.tsx](<../frontend/src/components/assistant/assistant-composer.tsx>) | Campo de pergunta, anexos e aviso do Assistente real. |
| [src/components/analysis/analysis-workspace.tsx](<../frontend/src/components/analysis/analysis-workspace.tsx>) | Painéis redimensionáveis; persiste visibilidade e larguras. Carregado sob demanda. |
| [src/components/analysis/panel-toggles.tsx](<../frontend/src/components/analysis/panel-toggles.tsx>) | Botões de liga/desliga dos painéis e tipo AnalysisLayout, separados para não puxar o `react-resizable-panels` na tela inicial. |
| [src/components/datasets/dataset-uploader.tsx](<../frontend/src/components/datasets/dataset-uploader.tsx>) | Envio paralelo de CSVs, progresso, estado de leitura, remoção e significado das colunas. |
| [src/components/documents/document-source-dialog.tsx](<../frontend/src/components/documents/document-source-dialog.tsx>) | Entrada por texto ou link; garante análise e chama os hooks de criação. |
| [src/components/chat/chat-message.tsx](<../frontend/src/components/chat/chat-message.tsx>) | Mensagens, streaming e chips de regras citadas. |
| [src/components/chat/processing-steps.tsx](<../frontend/src/components/chat/processing-steps.tsx>) | Etapas e falhas do processamento de documento. |
| [src/components/chat/chat-composer.tsx](<../frontend/src/components/chat/chat-composer.tsx>) | Compositor usado pela demonstração SystemDemo; o Assistente real usa AssistantComposer. |
| [src/components/chat/upload-dropzone.tsx](<../frontend/src/components/chat/upload-dropzone.tsx>) | Área demonstrativa de envio em SystemDemo; não é a entrada real do Assistente. |

## Documento, grifos e pesquisa

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [src/components/document/pdf-document.tsx](<../frontend/src/components/document/pdf-document.tsx>) | Carrega pdf.js/worker, dimensões, canvas e camada de texto; adia desenho de páginas distantes. |
| [src/components/document/pdf-viewer.tsx](<../frontend/src/components/document/pdf-viewer.tsx>) | Estrutura de rolagem, cabeçalho, sobreposições e páginas; não lê o formato PDF. |
| [src/components/document/pdf-toolbar.tsx](<../frontend/src/components/document/pdf-toolbar.tsx>) | Zoom, identificação da página e ações do visualizador. |
| [src/components/document/highlight-layer.tsx](<../frontend/src/components/document/highlight-layer.tsx>) | Desenha grifos, regra ativa e retângulos de pesquisa normalizados. |
| [src/components/document/create-rule-popover.tsx](<../frontend/src/components/document/create-rule-popover.tsx>) | Formulário de regra manual ancorado na seleção de texto. |
| [src/components/document/rule-legend.tsx](<../frontend/src/components/document/rule-legend.tsx>) | Legenda de tipos e controle do filtro por tipo. |
| [src/components/document/search-bar.tsx](<../frontend/src/components/document/search-bar.tsx>) | Entrada e navegação das ocorrências da busca no PDF. |
| [src/components/document/use-pdf-search.ts](<../frontend/src/components/document/use-pdf-search.ts>) | Obtém texto do PDF e retângulos das ocorrências para pesquisa visual. |

## Regras, filtros e conformidade

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [src/components/rules/rules-table.tsx](<../frontend/src/components/rules/rules-table.tsx>) | Tabela com seleção, hover, revisão humana, busca e coluna opcional de validação. |
| [src/components/rules/rules-header.tsx](<../frontend/src/components/rules/rules-header.tsx>) | Contagens, filtros, avisos e ações da lista. |
| [src/components/rules/rule-chip.tsx](<../frontend/src/components/rules/rule-chip.tsx>) | Citação clicável que conecta mensagem e destaque de regra. |
| [src/components/rules/types.ts](<../frontend/src/components/rules/types.ts>) | Tipos mínimos usados pelos componentes de regras. |
| [src/components/queries/query-badge.tsx](<../frontend/src/components/queries/query-badge.tsx>) | Estado/contagem da busca e acesso ao editor. |
| [src/components/queries/query-editor-dialog.tsx](<../frontend/src/components/queries/query-editor-dialog.tsx>) | Editor por formulário ou JSON; converte valores e envia o filtro ao backend. |
| [src/components/records/records-panel.tsx](<../frontend/src/components/records/records-panel.tsx>) | Visão geral de regras e alternância entre evidências da validação e registros da busca. |
| [src/components/validation/validation-badge.tsx](<../frontend/src/components/validation/validation-badge.tsx>) | Rótulo do resultado e ValidationSummary com contagens gerais. |
| [src/components/validation/validation-details.tsx](<../frontend/src/components/validation/validation-details.tsx>) | Explicação, dados faltantes, data e tabela de evidências paginada por base/resultado. |
| [src/components/knowledge/knowledge-base-view.tsx](<../frontend/src/components/knowledge/knowledge-base-view.tsx>) | Demonstração /regras, com dados fixos, busca por palavras e revisão em estado local. |
| [src/components/knowledge/answer-card.tsx](<../frontend/src/components/knowledge/answer-card.tsx>) | Resposta com citações da tela demonstrativa. |
| [src/components/knowledge/question-bar.tsx](<../frontend/src/components/knowledge/question-bar.tsx>) | Pergunta da tela demonstrativa. |

## Hooks e utilitários

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [src/lib/api/client.ts](<../frontend/src/lib/api/client.ts>) | openapi-fetch com cookies, unwrap, apiUrl e XMLHttpRequest para multipart com progresso. |
| [src/lib/api/errors.ts](<../frontend/src/lib/api/errors.ts>) | ApiError/errorMessage padronizam falhas HTTP, de rede e respostas inesperadas. |
| [src/lib/api/index.ts](<../frontend/src/lib/api/index.ts>) | Exportações públicas do cliente e dos tipos da API. |
| [src/lib/api/schema.d.ts](<../frontend/src/lib/api/schema.d.ts>) | Tipos gerados do OpenAPI. Atualizar com gen:api, nunca à mão. |
| [src/lib/auth.ts](<../frontend/src/lib/auth.ts>) | Sessão, login/cadastro/logout, perfil/senha, validação de next e formatação do nome. |
| [src/lib/analyses.ts](<../frontend/src/lib/analyses.ts>) | Consultas de análises, criação, upload/remoção de CSVs e polling das bases em processamento. |
| [src/lib/documents.ts](<../frontend/src/lib/documents.ts>) | Documentos/PDF, regras, histórico, atualização otimista da revisão e leitura de SSE. |
| [src/lib/performance.ts](<../frontend/src/lib/performance.ts>) | Consultas da página de desempenho (resumo, linha do tempo, chamadas), simulações e rótulos das janelas e operações. |
| [src/lib/queries.ts](<../frontend/src/lib/queries.ts>) | Operadores, descrição de filtros, geração/edição/execução de buscas e paginação de registros. |
| [src/lib/validation.ts](<../frontend/src/lib/validation.ts>) | Rótulos, comando de revalidação e consulta das evidências. |
| [src/lib/theme.ts](<../frontend/src/lib/theme.ts>) | Leitura, aplicação e persistência do tema e preferência do sistema. |
| [src/lib/use-persistent-state.ts](<../frontend/src/lib/use-persistent-state.ts>) | Estado React validado em localStorage e armazenamento dos painéis. |
| [src/lib/use-media-query.ts](<../frontend/src/lib/use-media-query.ts>) | Hook responsivo e distinção entre desktop e móvel. |
| [src/lib/floating.ts](<../frontend/src/lib/floating.ts>) | Posicionamento de elementos flutuantes ancorados em elementos ou seleções. |
| [src/lib/utils.ts](<../frontend/src/lib/utils.ts>) | cn combina classes condicionais e resolve conflitos Tailwind. |
| [src/lib/design/tokens.ts](<../frontend/src/lib/design/tokens.ts>) | Tipos, rótulos e cores de marca, regras, revisão e grifos. |
| [src/lib/design/color.ts](<../frontend/src/lib/design/color.ts>) | withAlpha adiciona transparência a cores hexadecimais. |
| [src/lib/demo/knowledge-base.ts](<../frontend/src/lib/demo/knowledge-base.ts>) | Documentos e regras fixos da demonstração. |

## Componentes visuais básicos

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [src/components/ui/avatar.tsx](<../frontend/src/components/ui/avatar.tsx>) | Avatar por iniciais. |
| [src/components/ui/badge.tsx](<../frontend/src/components/ui/badge.tsx>) | Badges de tipo/revisão e pontos de cor. |
| [src/components/ui/button.tsx](<../frontend/src/components/ui/button.tsx>) | Botão com variantes, tamanhos, ícones e loading. |
| [src/components/ui/card.tsx](<../frontend/src/components/ui/card.tsx>) | Superfície de agrupamento visual. |
| [src/components/ui/dialog.tsx](<../frontend/src/components/ui/dialog.tsx>) | Modal com dialog nativo, identificação acessível e controle de foco. |
| [src/components/ui/empty-state.tsx](<../frontend/src/components/ui/empty-state.tsx>) | Estado vazio com descrição e ação. |
| [src/components/ui/field.tsx](<../frontend/src/components/ui/field.tsx>) | Rótulos, descrições e erros de formulário. |
| [src/components/ui/icon-button.tsx](<../frontend/src/components/ui/icon-button.tsx>) | Botão de ícone com acessibilidade, loading e tooltip. |
| [src/components/ui/input.tsx](<../frontend/src/components/ui/input.tsx>) | Input e Textarea padronizados. |
| [src/components/ui/password-input.tsx](<../frontend/src/components/ui/password-input.tsx>) | Senha com controle de visibilidade. |
| [src/components/ui/popover.tsx](<../frontend/src/components/ui/popover.tsx>) | Painel flutuante e estilos comuns de sobreposição. |
| [src/components/ui/progress-bar.tsx](<../frontend/src/components/ui/progress-bar.tsx>) | Barra de progresso identificada por operação. |
| [src/components/ui/rule-type-select.tsx](<../frontend/src/components/ui/rule-type-select.tsx>) | Seletor dos tipos de regra. |
| [src/components/ui/select.tsx](<../frontend/src/components/ui/select.tsx>) | Select com aparência padronizada. |
| [src/components/ui/skeleton.tsx](<../frontend/src/components/ui/skeleton.tsx>) | Bloco de espera para conteúdo carregando. |
| [src/components/ui/spinner.tsx](<../frontend/src/components/ui/spinner.tsx>) | Indicador de operação em andamento. |
| [src/components/ui/toast.tsx](<../frontend/src/components/ui/toast.tsx>) | Provider e hook de notificações. |
| [src/components/ui/tooltip.tsx](<../frontend/src/components/ui/tooltip.tsx>) | Informação contextual ancorada. |

## Configuração, scripts e imagens

| Arquivo | Responsabilidade e pontos de entrada |
| --- | --- |
| [.env.example](<../frontend/.env.example>) | Modelo da URL pública da API, sem /api/v1 no final. |
| [.gitignore](<../frontend/.gitignore>) | Exclui dependências, build, ambientes e caches. |
| [AGENTS.md](<../frontend/AGENTS.md>) | Instruções para agentes, incluindo consulta da documentação local do Next antes de alterar código. |
| [README.md](<../frontend/README.md>) | Comandos do frontend e navegação da documentação. |
| [package.json](<../frontend/package.json>) | Dependências e scripts dev/build/start/lint/typecheck/gen:api. |
| [package-lock.json](<../frontend/package-lock.json>) | Resolução travada das dependências npm. |
| [next.config.ts](<../frontend/next.config.ts>) | Cache Components, prefetch parcial, compilador React e CSS/Turbopack. |
| [eslint.config.mjs](<../frontend/eslint.config.mjs>) | Regras ESLint com Next/TypeScript. |
| [tsconfig.json](<../frontend/tsconfig.json>) | Configuração TypeScript e alias @/. |
| [scripts/gen-api.mjs](<../frontend/scripts/gen-api.mjs>) | Gera schema.d.ts de uma URL ou arquivo OpenAPI usando openapi-typescript. |
| [public/logo-grifo.png](<../frontend/public/logo-grifo.png>) | Imagem pública da marca. |
| [public/brand/logo.png](<../frontend/public/brand/logo.png>) | Logo público no diretório brand. |
| [src/assets/og-logo.png](<../frontend/src/assets/og-logo.png>) | Logo da imagem de compartilhamento. |
| [src/app/icon.png](<../frontend/src/app/icon.png>) | Ícone da aplicação pelo mecanismo de metadados do Next. |
| [src/app/apple-icon.png](<../frontend/src/app/apple-icon.png>) | Ícone para atalhos em dispositivos Apple. |

## Código real e demonstrações

AssistantView usa a API. KnowledgeBaseView usa lib/demo/knowledge-base.ts e estado local. SystemDemo também é demonstrativo. ChatComposer e UploadDropzone pertencem à galeria; o envio real é coordenado pelo Assistente.

## Tipos e saídas geradas

A fonte do contrato é o OpenAPI do backend. schema.d.ts não substitui os schemas Pydantic. Depois de alterar um contrato, gere os tipos e adapte os consumidores. node_modules, frontend/.next, next-env.d.ts e arquivos .tsbuildinfo são saídas das ferramentas. O guia de desenvolvimento descreve os artefatos gerados que já estão versionados na raiz.
