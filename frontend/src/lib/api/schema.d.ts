// Arquivo gerado por scripts/gen-api.mjs a partir do OpenAPI do back-end.
// Não edite à mão: rode `npm run gen:api`.

export interface paths {
    "/api/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Verifica se a API e o banco respondem */
        get: operations["health_api_v1_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/register": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cria uma conta e já inicia a sessão */
        post: operations["register_api_v1_auth_register_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Entra com e-mail e senha */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Encerra a sessão atual */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Usuário da sessão atual */
        get: operations["me_api_v1_auth_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Atualiza o perfil */
        patch: operations["update_profile_api_v1_me_patch"];
        trace?: never;
    };
    "/api/v1/me/password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Troca a senha e encerra as outras sessões */
        post: operations["change_password_api_v1_me_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/analyses": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Análises do usuário, da mais recente à mais antiga */
        get: operations["list_analyses_api_v1_analyses_get"];
        put?: never;
        /** Cria uma análise vazia (as bases e os documentos são enviados depois) */
        post: operations["create_analysis_api_v1_analyses_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/analyses/{analysis_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** A análise com suas bases e documentos */
        get: operations["get_analysis_api_v1_analyses__analysis_id__get"];
        put?: never;
        post?: never;
        /** Exclui a análise, com as bases, os documentos, as regras e as conversas */
        delete: operations["delete_analysis_api_v1_analyses__analysis_id__delete"];
        options?: never;
        head?: never;
        /** Renomeia a análise */
        patch: operations["update_analysis_api_v1_analyses__analysis_id__patch"];
        trace?: never;
    };
    "/api/v1/analyses/{analysis_id}/datasets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Envia uma base de dados em CSV; devolve o schema detectado
         * @description Um arquivo por requisição. O separador (vírgula, ponto e vírgula, tab ou barra), a codificação e o tipo de cada coluna são detectados automaticamente.
         */
        post: operations["upload_dataset_api_v1_analyses__analysis_id__datasets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/datasets/{dataset_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Schema e linhas de amostra de uma base */
        get: operations["get_dataset_api_v1_datasets__dataset_id__get"];
        put?: never;
        post?: never;
        /**
         * Remove a base da análise
         * @description As buscas das regras que usavam esta base ficam sem base (dataset_id nulo).
         */
        delete: operations["delete_dataset_api_v1_datasets__dataset_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Documentos do usuário, do mais recente ao mais antigo */
        get: operations["list_documents_api_v1_documents_get"];
        put?: never;
        /**
         * Envia um arquivo (PDF, HTML ou TXT); a extração de regras continua em segundo plano
         * @description O arquivo é convertido na hora: um PDF sem texto (digitalizado), uma página sem conteúdo ou um formato desconhecido voltam com 422. HTML e TXT são diagramados em PDF, que é o que `GET /documents/{id}/file` devolve. Sem `analysis_id`, o documento ganha uma análise só dele.
         */
        post: operations["upload_document_api_v1_documents_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/text": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cria um documento a partir de texto colado */
        post: operations["create_text_document_api_v1_documents_text_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/url": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Baixa um documento (PDF ou página HTML) a partir de um link
         * @description Só http/https. Endereços internos ou privados são bloqueados, inclusive depois de redirecionamentos. O download tem tempo e tamanho limitados; falhas voltam com 422 e uma mensagem explicando o motivo (`fetch_error`).
         */
        post: operations["create_url_document_api_v1_documents_url_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Status do documento */
        get: operations["get_document_api_v1_documents__document_id__get"];
        put?: never;
        post?: never;
        /** Exclui o documento, as regras e a conversa */
        delete: operations["delete_document_api_v1_documents__document_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/file": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** O PDF original */
        get: operations["get_document_file_api_v1_documents__document_id__file_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/rules": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Regras do documento, na ordem do texto */
        get: operations["list_rules_api_v1_documents__document_id__rules_get"];
        put?: never;
        /** Cria uma regra a partir de um trecho selecionado na página */
        post: operations["create_rule_api_v1_documents__document_id__rules_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/rules/{rule_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Exclui a regra */
        delete: operations["delete_rule_api_v1_rules__rule_id__delete"];
        options?: never;
        head?: never;
        /** Atualiza situação, tipo, resumo ou comentário */
        patch: operations["update_rule_api_v1_rules__rule_id__patch"];
        trace?: never;
    };
    "/api/v1/documents/{document_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Histórico da conversa sobre o documento */
        get: operations["list_messages_api_v1_documents__document_id__messages_get"];
        put?: never;
        /**
         * Pergunta sobre o documento; a resposta chega por SSE
         * @description Eventos: `delta` ({text}) com pedaços da resposta, que podem conter marcadores de citação como [R3]; `done` (MessageOut) com a mensagem final, já sem os marcadores e com as regras citadas; `error` ({message}).
         */
        post: operations["send_message_api_v1_documents__document_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AnalysisCreateIn */
        AnalysisCreateIn: {
            /**
             * Title
             * @default Nova análise
             */
            title: string;
        };
        /** AnalysisDetailOut */
        AnalysisDetailOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Datasets */
            datasets: components["schemas"]["DatasetOut"][];
            /** Documents */
            documents: components["schemas"]["DocumentOut"][];
        };
        /** AnalysisOut */
        AnalysisOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string;
            /** Dataset Count */
            dataset_count: number;
            /** Document Count */
            document_count: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** AnalysisUpdateIn */
        AnalysisUpdateIn: {
            /** Title */
            title: string;
        };
        /** Body_upload_dataset_api_v1_analyses__analysis_id__datasets_post */
        Body_upload_dataset_api_v1_analyses__analysis_id__datasets_post: {
            /**
             * File
             * @description Arquivo CSV
             */
            file: string;
        };
        /** Body_upload_document_api_v1_documents_post */
        Body_upload_document_api_v1_documents_post: {
            /**
             * File
             * @description Arquivo PDF, HTML ou TXT
             */
            file: string;
            /**
             * Analysis Id
             * @description Análise do documento
             */
            analysis_id?: string | null;
        };
        /** CitedRule */
        CitedRule: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Type
             * @enum {string}
             */
            type: "obrigacao" | "proibicao" | "prazo" | "condicao" | "outro";
            /** Summary */
            summary: string;
        };
        /** DatasetColumn */
        DatasetColumn: {
            /** Name */
            name: string;
            /**
             * Type
             * @description Tipo inferido a partir de todos os valores da coluna.
             * @enum {string}
             */
            type: "integer" | "decimal" | "date" | "datetime" | "boolean" | "text";
            /**
             * Format
             * @description Números: br (1.234,56) ou us (1,234.56). Datas: iso ou br (dd/mm/aaaa).
             */
            format: string | null;
            /**
             * Null Count
             * @description Células vazias.
             */
            null_count: number;
            /**
             * Distinct Count
             * @description Valores distintos (contados até 1.000).
             */
            distinct_count: number;
            /** Examples */
            examples: string[];
            /**
             * Values
             * @description Todos os valores distintos, em colunas de categorias (até 30); senão vazio.
             */
            values: string[];
        };
        /** DatasetOut */
        DatasetOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Analysis Id
             * Format: uuid
             */
            analysis_id: string;
            /**
             * Name
             * @description Nome único na análise, usado pela IA para citar a base.
             */
            name: string;
            /** Filename */
            filename: string;
            /** Size Bytes */
            size_bytes: number;
            /** Encoding */
            encoding: string;
            /** Delimiter */
            delimiter: string;
            /** Row Count */
            row_count: number;
            /** Columns */
            columns: components["schemas"]["DatasetColumn"][];
            /**
             * Sample Rows
             * @description Primeiras linhas, como texto, na ordem de `columns` (None = célula vazia).
             */
            sample_rows: (string | null)[][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** DocumentOut */
        DocumentOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Analysis Id
             * Format: uuid
             */
            analysis_id: string;
            /** Title */
            title: string;
            /**
             * Source Type
             * @description Como o documento foi enviado.
             * @enum {string}
             */
            source_type: "pdf" | "text" | "html" | "url";
            /**
             * Source Url
             * @description Endereço de origem, se veio de um link.
             */
            source_url: string | null;
            /**
             * Status
             * @description processing (lendo o PDF), extracting_rules (IA analisando), ready ou error.
             * @enum {string}
             */
            status: "processing" | "extracting_rules" | "ready" | "error";
            /**
             * Status Message
             * @description Progresso ou motivo do erro, em português.
             */
            status_message: string | null;
            /** Page Count */
            page_count: number | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** ErrorDetail */
        ErrorDetail: {
            /**
             * Code
             * @description Código estável do erro, para tratamento no front.
             */
            code: string;
            /**
             * Message
             * @description Mensagem legível, em português.
             */
            message: string;
        };
        /**
         * ErrorResponse
         * @description Formato de todas as respostas de erro da API.
         */
        ErrorResponse: {
            error: components["schemas"]["ErrorDetail"];
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HealthResponse */
        HealthResponse: {
            /**
             * Status
             * @enum {string}
             */
            status: "ok" | "degraded";
            /** Database */
            database: boolean;
        };
        /**
         * HighlightBox
         * @description Retângulo do grifo, em frações da página (0 a 1), origem no canto superior esquerdo.
         */
        HighlightBox: {
            /** Page */
            page: number;
            /** X */
            x: number;
            /** Y */
            y: number;
            /** Width */
            width: number;
            /** Height */
            height: number;
        };
        /** LoginIn */
        LoginIn: {
            /** Email */
            email: string;
            /** Password */
            password: string;
        };
        /** MessageIn */
        MessageIn: {
            /** Content */
            content: string;
        };
        /** MessageOut */
        MessageOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Role
             * @enum {string}
             */
            role: "user" | "assistant";
            /**
             * Content
             * @description Texto sem os marcadores de citação [R1].
             */
            content: string;
            /** Citations */
            citations: components["schemas"]["CitedRule"][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** PasswordChangeIn */
        PasswordChangeIn: {
            /** Current Password */
            current_password: string;
            /** New Password */
            new_password: string;
        };
        /**
         * ProfileUpdateIn
         * @description Campos omitidos não mudam. Cargo e organização vazios são apagados.
         */
        ProfileUpdateIn: {
            /** Name */
            name?: string | null;
            /** Email */
            email?: string | null;
            /** Job Title */
            job_title?: string | null;
            /** Organization */
            organization?: string | null;
        };
        /** RegisterIn */
        RegisterIn: {
            /** Name */
            name: string;
            /** Email */
            email: string;
            /** Password */
            password: string;
        };
        /** RuleCreateIn */
        RuleCreateIn: {
            /**
             * Type
             * @enum {string}
             */
            type: "obrigacao" | "proibicao" | "prazo" | "condicao" | "outro";
            /** Summary */
            summary: string;
            /** Page */
            page: number;
            /**
             * Excerpt
             * @description Texto selecionado na página.
             */
            excerpt: string;
        };
        /** RuleOut */
        RuleOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Type
             * @enum {string}
             */
            type: "obrigacao" | "proibicao" | "prazo" | "condicao" | "outro";
            /**
             * Status
             * @enum {string}
             */
            status: "pendente" | "validada" | "rejeitada";
            /** Summary */
            summary: string;
            /** Excerpt */
            excerpt: string;
            /** Comment */
            comment: string | null;
            /**
             * Origin
             * @enum {string}
             */
            origin: "ia" | "manual";
            /**
             * Page
             * @description Página onde o trecho começa.
             */
            page: number | null;
            /** Boxes */
            boxes: components["schemas"]["HighlightBox"][];
        };
        /** RuleUpdateIn */
        RuleUpdateIn: {
            /** Type */
            type?: ("obrigacao" | "proibicao" | "prazo" | "condicao" | "outro") | null;
            /** Status */
            status?: ("pendente" | "validada" | "rejeitada") | null;
            /** Summary */
            summary?: string | null;
            /** Comment */
            comment?: string | null;
        };
        /** TextDocumentIn */
        TextDocumentIn: {
            /** Analysis Id */
            analysis_id?: string | null;
            /** Title */
            title?: string | null;
            /**
             * Content
             * @description Texto do documento.
             */
            content: string;
        };
        /** UrlDocumentIn */
        UrlDocumentIn: {
            /** Analysis Id */
            analysis_id?: string | null;
            /**
             * Url
             * @description Link http(s) do PDF ou da página.
             */
            url: string;
        };
        /** UserOut */
        UserOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Email */
            email: string;
            /** Job Title */
            job_title: string | null;
            /** Organization */
            organization: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    health_api_v1_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    register_api_v1_auth_register_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RegisterIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserOut"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserOut"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    me_api_v1_auth_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserOut"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    update_profile_api_v1_me_patch: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProfileUpdateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserOut"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    change_password_api_v1_me_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordChangeIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    list_analyses_api_v1_analyses_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnalysisOut"][];
                };
            };
        };
    };
    create_analysis_api_v1_analyses_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnalysisCreateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnalysisDetailOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_analysis_api_v1_analyses__analysis_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                analysis_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnalysisDetailOut"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_analysis_api_v1_analyses__analysis_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                analysis_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_analysis_api_v1_analyses__analysis_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                analysis_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnalysisUpdateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnalysisDetailOut"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_dataset_api_v1_analyses__analysis_id__datasets_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                analysis_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_dataset_api_v1_analyses__analysis_id__datasets_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DatasetOut"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_dataset_api_v1_datasets__dataset_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dataset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DatasetOut"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_dataset_api_v1_datasets__dataset_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                dataset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_documents_api_v1_documents_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentOut"][];
                };
            };
        };
    };
    upload_document_api_v1_documents_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_document_api_v1_documents_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentOut"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_text_document_api_v1_documents_text_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TextDocumentIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentOut"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    create_url_document_api_v1_documents_url_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UrlDocumentIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentOut"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    get_document_api_v1_documents__document_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentOut"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_document_api_v1_documents__document_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_document_file_api_v1_documents__document_id__file_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_rules_api_v1_documents__document_id__rules_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RuleOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_rule_api_v1_documents__document_id__rules_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RuleCreateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RuleOut"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    delete_rule_api_v1_rules__rule_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rule_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_rule_api_v1_rules__rule_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rule_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RuleUpdateIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RuleOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_messages_api_v1_documents__document_id__messages_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageOut"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    send_message_api_v1_documents__document_id__messages_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
}
