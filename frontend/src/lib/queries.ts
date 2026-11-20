"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ColumnType } from "@/lib/analyses";
import { api, type Schemas, unwrap } from "@/lib/api";
import { rememberColumns } from "@/lib/column-cache";
import type { DocumentInfo, Rule } from "@/lib/documents";
import { msg, type Translate } from "@/lib/i18n";

export type StructuredQuery = Schemas["StructuredQuery-Input"];
export type QueryCondition = Schemas["Condition"];
export type ConditionGroup = Schemas["ConditionGroup-Input"];
export type QueryOperator = QueryCondition["op"];
export type RuleQuery = Schemas["RuleQueryOut"];
export type RuleRecords = Schemas["RecordsOut"];
export type ConditionValue = QueryCondition["value"];

/** Em português; traduza ao exibir com `t(...)`. */
export const OPERATOR_LABELS: Record<QueryOperator, string> = {
  eq: msg("igual a"),
  ne: msg("diferente de"),
  gt: msg("maior que"),
  gte: msg("maior ou igual a"),
  lt: msg("menor que"),
  lte: msg("menor ou igual a"),
  between: msg("entre"),
  in: msg("é um de"),
  not_in: msg("não é nenhum de"),
  contains: msg("contém"),
  not_contains: msg("não contém"),
  starts_with: msg("começa com"),
  ends_with: msg("termina com"),
  is_null: msg("está vazio"),
  not_null: msg("está preenchido"),
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

function formatValue(value: ConditionValue, t: Translate): string {
  if (Array.isArray(value)) return value.map((v) => formatValue(v, t)).join(", ");
  if (typeof value === "boolean") return value ? t("sim") : t("não");
  if (typeof value === "number") return t.number(value);
  return value == null ? "" : `“${value}”`;
}

/**
 * Busca em palavras, para listas e tooltips, no idioma de `t`:
 * Valor maior que 50.000 e Garantia está vazio.
 */
export function describeQuery(
  query: { logic: "and" | "or"; conditions?: (QueryCondition | ConditionGroup)[] },
  t: Translate,
): string {
  const parts = (query.conditions ?? []).map((c) =>
    isGroup(c)
      ? `(${describeQuery(c, t)})`
      : NO_VALUE_OPERATORS.has(c.op)
        ? `${c.column} ${t(OPERATOR_LABELS[c.op])}`
        : c.op === "between" && Array.isArray(c.value)
          ? t("{column} entre {from} e {to}", {
              column: c.column,
              from: formatValue(c.value[0], t),
              to: formatValue(c.value[1], t),
            })
          : `${c.column} ${t(OPERATOR_LABELS[c.op])} ${formatValue(c.value, t)}`,
  );
  return parts.length ? parts.join(query.logic === "and" ? ` ${t("e")} ` : ` ${t("ou")} `) : t("todos os registros");
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

/** Prepara e salva a consulta; os registros são buscados apenas na regra selecionada. */
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
  const client = useQueryClient();
  return useQuery({
    queryKey: ruleKeys.records(ruleId ?? "", offset, limit),
    queryFn: async () => {
      const result = await unwrap(
        api.GET("/api/v1/rules/{rule_id}/records", {
          params: { path: { rule_id: ruleId! }, query: { offset, limit } },
        }),
      );
      rememberColumns(result.dataset_id, result.columns);
      if (result.query) {
        client.setQueriesData<Rule[]>({
          predicate: (q) => q.queryKey[0] === "documents" && q.queryKey[2] === "rules",
        }, (rules) => rules?.map((rule) => rule.id === ruleId ? { ...rule, query: result.query! } : rule));
      }
      return result;
    },
    enabled: !!ruleId && enabled,
    placeholderData: keepPreviousData,
    // Os registros só mudam com a busca da regra ou com as bases, e esses casos invalidam
    // esta consulta (`useReplaceRule`, `useDocument`, `useDeleteDataset`). Voltar a uma
    // regra ou página já vista usa o cache em vez de consultar o DuckDB de novo.
    staleTime: 5 * 60_000,
  });
}
