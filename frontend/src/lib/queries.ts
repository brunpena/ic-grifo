"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnType } from "@/lib/analyses";
import { api, type Schemas, unwrap } from "@/lib/api";
import type { DocumentInfo, Rule } from "@/lib/documents";

export type StructuredQuery = Schemas["StructuredQuery-Input"];
export type QueryCondition = Schemas["Condition"];
export type ConditionGroup = Schemas["ConditionGroup-Input"];
export type QueryOperator = QueryCondition["op"];
export type RuleQuery = Schemas["RuleQueryOut"];
export type RuleRecords = Schemas["RecordsOut"];
export type ConditionValue = QueryCondition["value"];

export const OPERATOR_LABELS: Record<QueryOperator, string> = {
  eq: "igual a",
  ne: "diferente de",
  gt: "maior que",
  gte: "maior ou igual a",
  lt: "menor que",
  lte: "menor ou igual a",
  between: "entre",
  in: "é um de",
  not_in: "não é nenhum de",
  contains: "contém",
  not_contains: "não contém",
  starts_with: "começa com",
  ends_with: "termina com",
  is_null: "está vazio",
  not_null: "está preenchido",
};

const ORDERED: QueryOperator[] = ["eq", "ne", "gt", "gte", "lt", "lte", "between", "in", "not_in", "is_null", "not_null"];

/** Mesma tabela do back (`query_engine.OPERATORS_BY_TYPE`). */
export const OPERATORS_BY_TYPE: Record<ColumnType, QueryOperator[]> = {
  integer: ORDERED,
  decimal: ORDERED,
  date: ORDERED,
  datetime: ORDERED,
  boolean: ["eq", "ne", "is_null", "not_null"],
  text: ["eq", "ne", "contains", "not_contains", "starts_with", "ends_with", "in", "not_in", "is_null", "not_null"],
};

export const LIST_OPERATORS = new Set<QueryOperator>(["between", "in", "not_in"]);
export const NO_VALUE_OPERATORS = new Set<QueryOperator>(["is_null", "not_null"]);

export function isGroup(item: QueryCondition | ConditionGroup): item is ConditionGroup {
  return "conditions" in item;
}

/** Busca sem grupos aninhados: é o que o editor visual consegue mostrar. */
export function isFlat(query: { conditions?: (QueryCondition | ConditionGroup)[] }) {
  return (query.conditions ?? []).every((c) => !isGroup(c));
}

function formatValue(value: ConditionValue): string {
  if (Array.isArray(value)) return value.map(formatValue).join(", ");
  if (typeof value === "boolean") return value ? "sim" : "não";
  if (typeof value === "number") return value.toLocaleString("pt-BR");
  return value == null ? "" : `“${value}”`;
}

/** Busca em português, para listas e tooltips: Valor maior que 50.000 e Garantia está vazio. */
export function describeQuery(query: { logic: "and" | "or"; conditions?: (QueryCondition | ConditionGroup)[] }): string {
  const parts = (query.conditions ?? []).map((c) =>
    isGroup(c)
      ? `(${describeQuery(c)})`
      : NO_VALUE_OPERATORS.has(c.op)
        ? `${c.column} ${OPERATOR_LABELS[c.op]}`
        : c.op === "between" && Array.isArray(c.value)
          ? `${c.column} entre ${formatValue(c.value[0])} e ${formatValue(c.value[1])}`
          : `${c.column} ${OPERATOR_LABELS[c.op]} ${formatValue(c.value)}`,
  );
  return parts.length ? parts.join(query.logic === "and" ? " e " : " ou ") : "todos os registros";
}

const ruleKeys = {
  rules: (documentId: string) => ["documents", documentId, "rules"] as const,
  records: (ruleId: string, offset: number, limit: number) => ["rules", ruleId, "records", offset, limit] as const,
  allRecords: (ruleId: string) => ["rules", ruleId, "records"] as const,
};

function useReplaceRule(documentId: string) {
  const queryClient = useQueryClient();
  return (rule: Rule) => {
    queryClient.setQueryData<Rule[]>(ruleKeys.rules(documentId), (list) =>
      list?.map((r) => (r.id === rule.id ? rule : r)),
    );
    void queryClient.invalidateQueries({ queryKey: ruleKeys.allRecords(rule.id) });
  };
}

/** Grava a busca (validada no back) e já traz o novo resultado. */
export function useSetRuleQuery(documentId: string) {
  const replace = useReplaceRule(documentId);
  return useMutation({
    mutationFn: ({ ruleId, query }: { ruleId: string; query: StructuredQuery }) =>
      unwrap(api.PUT("/api/v1/rules/{rule_id}/query", { params: { path: { rule_id: ruleId } }, body: query })),
    onSuccess: replace,
  });
}

export function useRunRuleQuery(documentId: string) {
  const replace = useReplaceRule(documentId);
  return useMutation({
    mutationFn: (ruleId: string) =>
      unwrap(api.POST("/api/v1/rules/{rule_id}/query/run", { params: { path: { rule_id: ruleId } } })),
    onSuccess: replace,
  });
}

export function useDeleteRuleQuery(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ruleId: string) =>
      unwrap(api.DELETE("/api/v1/rules/{rule_id}/query", { params: { path: { rule_id: ruleId } } })),
    onSuccess: (_result, ruleId) =>
      queryClient.setQueryData<Rule[]>(ruleKeys.rules(documentId), (list) =>
        list?.map((r) => (r.id === ruleId ? { ...r, query: null } : r)),
      ),
  });
}

/** Pede à IA as buscas das regras; o documento volta a ser acompanhado até ficar pronto. */
export function useGenerateQueries(documentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (overwrite: boolean) =>
      unwrap(
        api.POST("/api/v1/documents/{document_id}/queries", {
          params: { path: { document_id: documentId } },
          body: { overwrite },
        }),
      ),
    onSuccess: (doc) => {
      queryClient.setQueryData<DocumentInfo>(["documents", doc.id], doc);
      void queryClient.invalidateQueries({ queryKey: ruleKeys.rules(doc.id) });
    },
  });
}

/** Registros encontrados pela busca da regra, uma página por vez. */
export function useRuleRecords(ruleId: string | null, offset: number, limit: number, enabled = true) {
  return useQuery({
    queryKey: ruleKeys.records(ruleId ?? "", offset, limit),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/rules/{rule_id}/records", {
          params: { path: { rule_id: ruleId! }, query: { offset, limit } },
        }),
      ),
    enabled: !!ruleId && enabled,
    placeholderData: keepPreviousData,
  });
}
