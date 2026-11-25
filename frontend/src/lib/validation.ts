"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { analysisKeys } from "@/lib/analyses";
import { api, type Schemas, unwrap } from "@/lib/api";
import { msg } from "@/lib/i18n";

export type RuleValidation = Schemas["RuleValidationOut"];
export type ValidationStatus = RuleValidation["status"];
export type RecordVerdict = Schemas["ValidationRecord"]["verdict"];

/** Em português; traduza ao exibir com `t(...)`. */
export const VALIDATION_LABELS: Record<ValidationStatus, string> = {
  conforme: msg("Conforme"), violacao: msg("Violação"), inconclusiva: msg("Inconclusiva"),
  nao_aplicavel: msg("Não se aplica"), erro: msg("Erro na verificação"),
  desatualizada: msg("Validar novamente"), ignorada: msg("Desconsiderada"),
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
    // Invalidada quando a validação roda de novo ou o documento volta a ficar pronto.
    staleTime: 5 * 60_000,
  });
}
