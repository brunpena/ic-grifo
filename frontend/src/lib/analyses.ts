"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, postFormWithProgress, type Schemas, type UploadProgress, unwrap } from "@/lib/api";
import { rememberColumns } from "@/lib/column-cache";
import { msg } from "@/lib/i18n";

export type Analysis = Schemas["AnalysisDetailOut"];
export type AnalysisSummary = Schemas["AnalysisOut"];
export type Dataset = Schemas["DatasetOut"];
export type DatasetColumn = Schemas["DatasetColumn"];
export type ColumnType = DatasetColumn["type"];

export const analysisKeys = {
  list: ["analyses"] as const,
  detail: (id: string) => ["analyses", id] as const,
};

/** Em português; traduza ao exibir com `t(...)`. */
export const COLUMN_TYPE_LABELS: Record<ColumnType, string> = {
  integer: msg("Inteiro"),
  decimal: msg("Decimal"),
  date: msg("Data"),
  datetime: msg("Data e hora"),
  boolean: msg("Sim/não"),
  text: msg("Texto"),
};

export function useAnalyses() {
  return useQuery({ queryKey: analysisKeys.list, queryFn: () => unwrap(api.GET("/api/v1/analyses")) });
}

/**
 * Quando uma base termina de ser lida, o servidor volta a preparar as buscas dos documentos
 * já prontos da análise. Durante esta janela, `useDocument` consulta o documento para
 * perceber essa mudança; fora dela, um documento pronto não é consultado de novo.
 */
const DOCUMENT_WATCH_MS = 10_000;
const watchedUntil = new Map<string, number>();

export function isWatchingDocuments(analysisId: string | undefined) {
  return !!analysisId && (watchedUntil.get(analysisId) ?? 0) > Date.now();
}

export function useAnalysis(id: string | null) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: analysisKeys.detail(id ?? ""),
    queryFn: async () => {
      const before = queryClient.getQueryData<Analysis>(analysisKeys.detail(id!));
      const analysis = await unwrap(api.GET("/api/v1/analyses/{analysis_id}", { params: { path: { analysis_id: id! } } }));
      // O cabeçalho já vem do processamento inicial: guarda para os skeletons das tabelas.
      for (const dataset of analysis.datasets) rememberColumns(dataset.id, dataset.columns.map((c) => c.name));
      const finished = analysis.datasets.some(
        (d) => d.status === "ready" && before?.datasets.find((p) => p.id === d.id)?.status === "processing",
      );
      if (finished) {
        watchedUntil.set(id!, Date.now() + DOCUMENT_WATCH_MS);
        void queryClient.invalidateQueries({
          predicate: (q) =>
            q.queryKey[0] === "documents" &&
            q.queryKey.length === 2 &&
            (q.state.data as { analysis_id?: string } | undefined)?.analysis_id === id,
        });
      }
      return analysis;
    },
    enabled: !!id,
    // Acompanha as bases que o servidor ainda está lendo.
    refetchInterval: (query) => (query.state.data?.datasets.some((d) => d.status === "processing") ? 1500 : false),
  });
}

export function useCreateAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (title?: string) => unwrap(api.POST("/api/v1/analyses", { body: { title: title ?? "Nova análise" } })),
    onSuccess: (analysis) => {
      queryClient.setQueryData(analysisKeys.detail(analysis.id), analysis);
      void queryClient.invalidateQueries({ queryKey: analysisKeys.list, exact: true });
    },
  });
}

export async function closeAnalysis(id: string, keepalive = false): Promise<void> {
  await unwrap(api.POST("/api/v1/analyses/{analysis_id}/close", {
    params: { path: { analysis_id: id } },
    keepalive,
  }));
}

export function useCloseAnalysis() {
  return useMutation({ mutationFn: (id: string) => closeAnalysis(id) });
}

/** Envia um CSV. Use uma chamada por arquivo: cada um tem seu próprio erro. A base volta
 * em `processing` e o servidor a lê em segundo plano (ver `useAnalysis`). */
export function useUploadDataset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      analysisId,
      file,
      onProgress,
    }: {
      analysisId: string;
      file: File;
      /** Bytes já enviados; depois do envio, o servidor ainda lê a base. */
      onProgress: (progress: UploadProgress) => void;
    }) => {
      const form = new FormData();
      form.append("file", file);
      return postFormWithProgress<Dataset>(`/api/v1/analyses/${analysisId}/datasets`, form, onProgress);
    },
    onSuccess: (dataset) => {
      queryClient.setQueryData<Analysis>(analysisKeys.detail(dataset.analysis_id), (analysis) =>
        analysis ? { ...analysis, datasets: [...analysis.datasets, dataset] } : analysis,
      );
      void queryClient.invalidateQueries({ queryKey: analysisKeys.list, exact: true });
    },
  });
}

export function useDeleteDataset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (dataset: Dataset) =>
      unwrap(api.DELETE("/api/v1/datasets/{dataset_id}", { params: { path: { dataset_id: dataset.id } } })),
    onSuccess: (_result, dataset) => {
      queryClient.setQueryData<Analysis>(analysisKeys.detail(dataset.analysis_id), (analysis) =>
        analysis ? { ...analysis, datasets: analysis.datasets.filter((d) => d.id !== dataset.id) } : analysis,
      );
      void queryClient.invalidateQueries({ queryKey: analysisKeys.list, exact: true });
      // O servidor marca com erro as buscas que usavam a base e invalida as validações.
      void queryClient.invalidateQueries({
        predicate: (q) => q.queryKey[0] === "documents" && q.queryKey[2] === "rules",
      });
      void queryClient.invalidateQueries({ queryKey: ["rules"] });
      void queryClient.invalidateQueries({ queryKey: ["validation-records"] });
    },
  });
}

export function isCsvFile(file: File) {
  return /\.(csv|tsv|txt|crdownload)$/i.test(file.name) || file.type === "text/csv";
}
