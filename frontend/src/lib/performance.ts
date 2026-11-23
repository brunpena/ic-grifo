"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Schemas, unwrap } from "@/lib/api";
import { msg } from "@/lib/i18n";

export type PerformanceSummary = Schemas["PerformanceSummaryOut"];
export type RouteStats = Schemas["RouteStats"];
export type RequestLog = Schemas["RequestLogOut"];
export type Timeline = Schemas["TimelineOut"];
export type SimulationOperation = Schemas["SimulationOperationOut"];
export type SimulationInput = Schemas["SimulationIn"];
export type SimulationResult = Schemas["SimulationOut"];
export type SimulationRun = Schemas["SimulationRunOut"];
export type MetricsSource = "app" | "simulacao" | "all";

export type MetricsFilter = { sinceHours: number; source: MetricsSource };

/** Janelas de tempo oferecidas na página (em horas). */
export const WINDOWS: { hours: number; label: string }[] = [
  { hours: 1, label: msg("Última hora") },
  { hours: 6, label: msg("Últimas 6 horas") },
  { hours: 24, label: msg("Últimas 24 horas") },
  { hours: 24 * 7, label: msg("Últimos 7 dias") },
  { hours: 24 * 30, label: msg("Últimos 30 dias") },
];

export const SOURCES: { value: MetricsSource; label: string }[] = [
  { value: "app", label: msg("Uso real") },
  { value: "simulacao", label: msg("Simulações") },
  { value: "all", label: msg("Tudo") },
];

/** Nomes das operações da simulação, pela chave do back. Em português; traduza ao exibir. */
export const OPERATION_LABELS: Record<string, string> = {
  health: msg("Saúde da API (sem login)"),
  auth_me: msg("Usuário da sessão"),
  analyses_list: msg("Listar análises"),
  analysis_detail: msg("Abrir uma análise"),
  documents_list: msg("Listar documentos"),
  document_detail: msg("Status de um documento"),
  document_file: msg("Baixar o PDF de um documento"),
  document_rules: msg("Regras de um documento"),
  document_messages: msg("Conversa de um documento"),
  rule_records: msg("Registros encontrados por uma regra"),
  custom: msg("Caminho personalizado (GET)"),
};

const keys = {
  all: ["performance"] as const,
  summary: (f: MetricsFilter) => ["performance", "summary", f] as const,
  timeline: (f: MetricsFilter, route?: RouteKey | null) => ["performance", "timeline", f, route ?? null] as const,
  requests: (f: MetricsFilter, route: RouteKey | null, order: string) =>
    ["performance", "requests", f, route, order] as const,
  operations: ["performance", "operations"] as const,
  simulations: ["performance", "simulations"] as const,
};

export type RouteKey = { method: string; route: string };

const query = (f: MetricsFilter) => ({ since_hours: f.sinceHours, source: f.source });

export function usePerformanceSummary(filter: MetricsFilter) {
  return useQuery({
    queryKey: keys.summary(filter),
    queryFn: () => unwrap(api.GET("/api/v1/performance/summary", { params: { query: query(filter) } })),
    refetchInterval: 30_000,
  });
}

export function useTimeline(filter: MetricsFilter, route: RouteKey | null) {
  return useQuery({
    queryKey: keys.timeline(filter, route),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/performance/timeline", {
          params: { query: { ...query(filter), method: route?.method, route: route?.route } },
        }),
      ),
    refetchInterval: 30_000,
  });
}

export function useRequestLogs(filter: MetricsFilter, route: RouteKey | null, order: "slowest" | "recent") {
  return useQuery({
    queryKey: keys.requests(filter, route, order),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/performance/requests", {
          params: { query: { ...query(filter), method: route?.method, route: route?.route, order, limit: 25 } },
        }),
      ),
    enabled: !!route,
  });
}

export function useSimulationOperations() {
  return useQuery({
    queryKey: keys.operations,
    queryFn: () => unwrap(api.GET("/api/v1/performance/operations")),
    staleTime: Infinity,
  });
}

export function useSimulationRuns() {
  return useQuery({ queryKey: keys.simulations, queryFn: () => unwrap(api.GET("/api/v1/performance/simulations")) });
}

export function useRunSimulation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SimulationInput) => unwrap(api.POST("/api/v1/performance/simulations", { body })),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.all }),
  });
}
