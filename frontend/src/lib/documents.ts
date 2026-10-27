"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { analysisKeys } from "@/lib/analyses";
import { api, ApiError, apiUrl, type Schemas, unwrap } from "@/lib/api";

export type DocumentInfo = Schemas["DocumentOut"];
export type Rule = Schemas["RuleOut"];
export type ChatMessage = Schemas["MessageOut"];
export type RuleStatus = Rule["status"];
export type RuleType = Rule["type"];

const keys = {
  list: ["documents"] as const,
  doc: (id: string) => ["documents", id] as const,
  file: (id: string) => ["documents", id, "file"] as const,
  rules: (id: string) => ["documents", id, "rules"] as const,
  messages: (id: string) => ["documents", id, "messages"] as const,
};


export function useDocuments() {
  return useQuery({ queryKey: keys.list, queryFn: () => unwrap(api.GET("/api/v1/documents")) });
}

/** Status do documento; consulta de novo a cada 1,5 s enquanto ele é processado. */
export function useDocument(id: string | null) {
  const client = useQueryClient();
  const previous = useRef<string | null>(null);
  const query = useQuery({
    queryKey: keys.doc(id ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/documents/{document_id}", { params: { path: { document_id: id! } } })),
    enabled: !!id,
    refetchInterval: (query) => query.state.data?.status === "error" ? false : query.state.data?.status === "ready" ? 5000 : 1500,
  });
  const status = query.data?.status;
  const analysisId = query.data?.analysis_id;
  useEffect(() => {
    const current = `${id}:${status}`;
    if (status === "ready" && previous.current !== current) {
      void client.invalidateQueries({ queryKey: keys.rules(id!) });
      void client.invalidateQueries({ queryKey: ["validation-records"] });
      if (analysisId) void client.invalidateQueries({ queryKey: analysisKeys.detail(analysisId) });
    }
    previous.current = current;
  }, [id, status, analysisId, client]);
  return query;
}

/** Formatos aceitos no envio de arquivo (o back escolhe o conversor). */
export const DOCUMENT_ACCEPT = "application/pdf,.pdf,text/html,.html,.htm,text/plain,.txt";

export function isDocumentFile(file: File) {
  return /\.(pdf|html?|txt)$/i.test(file.name) || ["application/pdf", "text/html", "text/plain"].includes(file.type);
}

export const isPdfFile = (file: File) => file.type === "application/pdf" || /\.pdf$/i.test(file.name);

function useDocumentCreated() {
  const queryClient = useQueryClient();
  return (doc: DocumentInfo) => {
    queryClient.setQueryData(keys.doc(doc.id), doc);
    void queryClient.invalidateQueries({ queryKey: keys.list, exact: true });
    void queryClient.invalidateQueries({ queryKey: analysisKeys.detail(doc.analysis_id) });
    void queryClient.invalidateQueries({ queryKey: analysisKeys.list, exact: true });
  };
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  const onCreated = useDocumentCreated();
  return useMutation({
    /** Sem `analysisId`, o back cria uma análise só para o documento. */
    mutationFn: ({ file, analysisId }: { file: File; analysisId?: string | null }) =>
      unwrap(
        api.POST("/api/v1/documents", {
          body: { file: file as unknown as string, analysis_id: analysisId },
          bodySerializer: () => {
            const form = new FormData();
            form.append("file", file);
            if (analysisId) form.append("analysis_id", analysisId);
            return form;
          },
        }),
      ),
    onSuccess: (doc, { file }) => {
      onCreated(doc);
      // O PDF enviado é o mesmo que o back guardou: evita baixá-lo de volta.
      if (isPdfFile(file)) queryClient.setQueryData(keys.file(doc.id), file);
    },
  });
}

export function useCreateTextDocument() {
  const onCreated = useDocumentCreated();
  return useMutation({
    mutationFn: (body: { analysis_id?: string | null; title?: string | null; content: string }) =>
      unwrap(api.POST("/api/v1/documents/text", { body })),
    onSuccess: onCreated,
  });
}

/** O back baixa o link (PDF ou HTML) com proteção contra endereços internos. */
export function useCreateUrlDocument() {
  const onCreated = useDocumentCreated();
  return useMutation({
    mutationFn: (body: { analysis_id?: string | null; url: string }) =>
      unwrap(api.POST("/api/v1/documents/url", { body })),
    onSuccess: onCreated,
  });
}

/** O PDF exibido de um documento (o original ou o diagramado a partir de texto/HTML). */
export function useDocumentFile(doc: DocumentInfo | undefined) {
  return useQuery({
    queryKey: keys.file(doc?.id ?? ""),
    queryFn: () => fetchDocumentFile(doc!),
    enabled: !!doc,
    staleTime: Infinity,
    gcTime: 10 * 60 * 1000,
  });
}

/** Baixa o PDF de um documento já enviado, para reabri-lo no visualizador. */
export async function fetchDocumentFile(doc: DocumentInfo): Promise<File> {
  const response = await fetch(apiUrl(`/api/v1/documents/${doc.id}/file`), { credentials: "include" });
  if (!response.ok) throw await ApiError.fromResponse(response);
  const name = doc.source_type === "pdf" ? doc.title : `${doc.title}.pdf`;
  return new File([await response.blob()], name, { type: "application/pdf" });
}

export function useRules(documentId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: keys.rules(documentId ?? ""),
    queryFn: () =>
      unwrap(api.GET("/api/v1/documents/{document_id}/rules", { params: { path: { document_id: documentId! } } })),
    enabled: !!documentId && enabled,
    staleTime: 0,
    refetchInterval: enabled ? 5000 : false,
  });
}

/** Muda a situação (ou o tipo/resumo) de uma regra, atualizando a tabela na hora. */
export function useUpdateRule(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; status?: RuleStatus; type?: RuleType; summary?: string }) =>
      unwrap(api.PATCH("/api/v1/rules/{rule_id}", { params: { path: { rule_id: id } }, body })),
    onMutate: async ({ id, ...changes }) => {
      await queryClient.cancelQueries({ queryKey: keys.rules(documentId) });
      const previous = queryClient.getQueryData<Rule[]>(keys.rules(documentId));
      queryClient.setQueryData<Rule[]>(keys.rules(documentId), (list) =>
        list?.map((r) => (r.id === id ? { ...r, ...changes } : r)),
      );
      return { previous };
    },
    onError: (_error, _vars, context) => queryClient.setQueryData(keys.rules(documentId), context?.previous),
    onSuccess: (rule) =>
      queryClient.setQueryData<Rule[]>(keys.rules(documentId), (list) => list?.map((r) => (r.id === rule.id ? rule : r))),
  });
}

export function useCreateRule(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { type: RuleType; summary: string; page: number; excerpt: string }) =>
      unwrap(api.POST("/api/v1/documents/{document_id}/rules", { params: { path: { document_id: documentId } }, body })),
    onSuccess: (rule) =>
      queryClient.setQueryData<Rule[]>(keys.rules(documentId), (list) =>
        [...(list ?? []), rule].sort((a, b) => (a.page ?? 0) - (b.page ?? 0)),
      ),
  });
}

export function useMessages(documentId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: keys.messages(documentId ?? ""),
    queryFn: () =>
      unwrap(api.GET("/api/v1/documents/{document_id}/messages", { params: { path: { document_id: documentId! } } })),
    enabled: !!documentId && enabled,
  });
}

export function invalidateMessages(queryClient: ReturnType<typeof useQueryClient>, documentId: string) {
  return queryClient.invalidateQueries({ queryKey: keys.messages(documentId) });
}

/** Tira os marcadores de citação ([R3]) do texto, inclusive um marcador ainda incompleto no fim. */
export function stripCitations(text: string) {
  return text.replace(/\s*\[R\d+(?:\s*,\s*R\d+)*\]/g, "").replace(/\s*\[R?[\dR,\s]*$/, "");
}

type StreamHandlers = {
  onDelta: (text: string) => void;
  onDone: (message: ChatMessage) => void;
};

/** Envia uma pergunta e lê a resposta por SSE (o EventSource não aceita POST). */
export async function streamMessage(documentId: string, content: string, handlers: StreamHandlers, signal?: AbortSignal) {
  const response = await fetch(apiUrl(`/api/v1/documents/${documentId}/messages`), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ content }),
    signal,
  }).catch(() => {
    throw ApiError.network();
  });
  if (!response.ok || !response.body) throw await ApiError.fromResponse(response);

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const events = buffer.split(/\r?\n\r?\n/);
    buffer = events.pop() ?? "";
    for (const raw of events) {
      let event = "message";
      const data: string[] = [];
      for (const line of raw.split(/\r?\n/)) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
      if (!data.length) continue;
      const payload = JSON.parse(data.join("\n"));
      if (event === "delta") handlers.onDelta(payload.text);
      else if (event === "done") handlers.onDone(payload);
      else if (event === "error") throw new ApiError("chat_error", payload.message, 200);
    }
  }
}
