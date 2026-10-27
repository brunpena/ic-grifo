"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { analysisKeys } from "@/lib/analyses";
import { api, type Schemas, unwrap } from "@/lib/api";

export type RuleValidation = Schemas["RuleValidationOut"];
export type ValidationStatus = RuleValidation["status"];
export type RecordVerdict = Schemas["ValidationRecord"]["verdict"];

export const VALIDATION_LABELS: Record<ValidationStatus, string> = {
  conforme: "Conforme", violacao: "Violação", inconclusiva: "Inconclusiva",
  nao_aplicavel: "Não se aplica", erro: "Erro na verificação",
  desatualizada: "Validar novamente", ignorada: "Desconsiderada",
};

export function useValidateDocument(documentId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (refreshColumns: boolean) => unwrap(api.POST("/api/v1/documents/{document_id}/validation", {
      params: { path: { document_id: documentId }, query: { refresh_columns: refreshColumns } },
    })),
    onSuccess: (doc) => {
      client.setQueryData(["documents", doc.id], doc);
      void client.invalidateQueries({ queryKey: ["documents", doc.id, "rules"] });
      void client.invalidateQueries({ queryKey: ["validation-records"] });
      void client.invalidateQueries({ queryKey: analysisKeys.detail(doc.analysis_id) });
    },
  });
}

export function useValidationRecords(ruleId: string, datasetId: string | null, offset: number, verdict: RecordVerdict | "") {
  return useQuery({
    queryKey: ["validation-records", ruleId, datasetId, offset, verdict],
    queryFn: () => unwrap(api.GET("/api/v1/rules/{rule_id}/validation/records", {
      params: { path: { rule_id: ruleId }, query: {
        dataset_id: datasetId!, offset, limit: 100, ...(verdict ? { verdict } : {}),
      } },
    })),
    enabled: !!datasetId,
    placeholderData: keepPreviousData,
    staleTime: 0,
  });
}
