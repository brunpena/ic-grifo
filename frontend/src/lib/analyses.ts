"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, postFormWithProgress, type Schemas, type UploadProgress, unwrap } from "@/lib/api";

export type Analysis = Schemas["AnalysisDetailOut"];
export type AnalysisSummary = Schemas["AnalysisOut"];
export type Dataset = Schemas["DatasetOut"];
export type DatasetColumn = Schemas["DatasetColumn"];
export type ColumnType = DatasetColumn["type"];

export const analysisKeys = {
  list: ["analyses"] as const,
  detail: (id: string) => ["analyses", id] as const,
};

export const COLUMN_TYPE_LABELS: Record<ColumnType, string> = {
  integer: "Inteiro",
  decimal: "Decimal",
  date: "Data",
  datetime: "Data e hora",
  boolean: "Sim/não",
  text: "Texto",
};

export function useAnalyses() {
  return useQuery({ queryKey: analysisKeys.list, queryFn: () => unwrap(api.GET("/api/v1/analyses")) });
}

export function useAnalysis(id: string | null) {
  return useQuery({
    queryKey: analysisKeys.detail(id ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/analyses/{analysis_id}", { params: { path: { analysis_id: id! } } })),
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
    },
  });
}

export function isCsvFile(file: File) {
  return /\.(csv|tsv|txt|crdownload)$/i.test(file.name) || file.type === "text/csv";
}
