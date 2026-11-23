"use client";

import { ArrowDown, ArrowUp, Gauge, Lightbulb, RefreshCw, X } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { IconButton } from "@/components/ui/icon-button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { intlLocale, msg, type Translate, useT } from "@/lib/i18n";
import {
  type MetricsFilter,
  type MetricsSource,
  type RouteKey,
  type RouteStats,
  SOURCES,
  usePerformanceSummary,
  useRequestLogs,
  useTimeline,
  WINDOWS,
} from "@/lib/performance";
import { cn } from "@/lib/utils";
import { TimelineChart } from "./charts";
import { formatBytes, formatCount, formatMs } from "./format";
import { SimulationPanel } from "./simulation-panel";

type SortKey = "total_ms" | "p95_ms" | "avg_ms" | "count" | "avg_db_ms" | "avg_db_queries" | "server_errors";

export function PerformanceView() {
  const t = useT();
  const [filter, setFilter] = useState<MetricsFilter>({ sinceHours: 24, source: "app" });
  const [selected, setSelected] = useState<RouteKey | null>(null);
  const summary = usePerformanceSummary(filter);
  const timeline = useTimeline(filter, null);

  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 pt-8 pb-12 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold">{t("Desempenho")}</h1>
            <p className="text-[13px] text-foreground-muted">
              {t("Quanto tempo cada tipo de requisição leva, onde o tempo é gasto e simulações de carga.")}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select
              aria-label={t("Janela de tempo")}
              value={filter.sinceHours}
              onChange={(e) => setFilter((f) => ({ ...f, sinceHours: Number(e.target.value) }))}
            >
              {WINDOWS.map((w) => (
                <option key={w.hours} value={w.hours}>{t(w.label)}</option>
              ))}
            </Select>
            <Select
              aria-label={t("Origem das requisições")}
              value={filter.source}
              onChange={(e) => setFilter((f) => ({ ...f, source: e.target.value as MetricsSource }))}
            >
              {SOURCES.map((s) => (
                <option key={s.value} value={s.value}>{t(s.label)}</option>
              ))}
            </Select>
            <IconButton
              aria-label={t("Atualizar")}
              onClick={() => {
                void summary.refetch();
                void timeline.refetch();
              }}
              icon={
                <RefreshCw
                  size={16}
                  strokeWidth={1.75}
                  className={cn(summary.isFetching && "animate-spin motion-reduce:animate-none")}
                />
              }
            />
          </div>
        </div>

        {summary.isError ? (
          <p role="alert" className="text-sm text-danger">{errorMessage(summary.error, t)}</p>
        ) : summary.isPending ? (
          <div role="status" aria-busy className="grid gap-3 sm:grid-cols-5">
            <span className="sr-only">{t("Carregando")}</span>
            {[1, 2, 3, 4, 5].map((n) => <Skeleton key={n} className="h-20" />)}
          </div>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
              <Stat label={t("Requisições")} value={formatCount(summary.data.totals.count, t.locale)} />
              <Stat label={t("Média")} value={formatMs(summary.data.totals.avg_ms, t.locale)} />
              <Stat label="p95" value={formatMs(summary.data.totals.p95_ms, t.locale)} hint={t("95% terminam em até")} />
              <Stat label={t("Tempo médio no banco")} value={formatMs(summary.data.avg_db_ms, t.locale)} />
              <Stat
                label={t("Erros do servidor (5xx)")}
                value={formatCount(summary.data.server_errors, t.locale)}
                tone={summary.data.server_errors ? "danger" : undefined}
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
              <Card className="flex flex-col gap-3">
                <h2 className="text-sm font-semibold">{t("Tempo das requisições")}</h2>
                {timeline.data ? (
                  <TimelineChart points={timeline.data.points} bucketMinutes={timeline.data.bucket_minutes} />
                ) : (
                  <Skeleton className="h-40" />
                )}
              </Card>
              <Card className="flex flex-col gap-3">
                <h2 className="text-sm font-semibold">{t("Onde o tempo é gasto")}</h2>
                <p className="text-xs text-foreground-muted">{t("Soma das durações por recurso da API.")}</p>
                <CategoryBars categories={summary.data.categories} />
              </Card>
            </div>

            <Card className="flex flex-col gap-3 p-0">
              <div className="flex flex-col gap-1 px-4 pt-4">
                <h2 className="text-sm font-semibold">{t("Tipos de requisição")}</h2>
                <p className="text-xs text-foreground-muted">
                  {t("Cada linha é um método + rota. Clique para ver as chamadas mais lentas e sugestões.")}
                </p>
              </div>
              {summary.data.routes.length ? (
                <RoutesTable routes={summary.data.routes} selected={selected} onSelect={setSelected} />
              ) : (
                <EmptyState
                  icon={Gauge}
                  title={t("Nenhuma requisição registrada nesta janela")}
                  description={t("Use o sistema ou rode uma simulação abaixo para gerar medições.")}
                />
              )}
            </Card>

            {selected && (
              <RouteDetail
                filter={filter}
                route={selected}
                stats={summary.data.routes.find((r) => r.method === selected.method && r.route === selected.route)}
                onClose={() => setSelected(null)}
              />
            )}
          </>
        )}

        <SimulationPanel />
      </div>
    </div>
  );
}

function Stat({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "danger" }) {
  return (
    <Card className="flex flex-col gap-1">
      <span className="text-xs text-foreground-muted">{label}</span>
      <span className={cn("text-xl font-semibold tabular-nums", tone === "danger" && "text-danger")}>{value}</span>
      {hint && <span className="text-[11px] text-foreground-subtle">{hint}</span>}
    </Card>
  );
}

function CategoryBars({ categories }: { categories: { category: string; total_ms: number; count: number; p95_ms?: number | null }[] }) {
  const t = useT();
  const total = categories.reduce((sum, c) => sum + c.total_ms, 0) || 1;
  const top = Math.max(...categories.map((c) => c.total_ms), 1);
  return (
    <ul className="flex flex-col gap-2.5">
      {categories.map((c) => (
        <li key={c.category} className="flex flex-col gap-1" title={`${c.count} · p95 ${formatMs(c.p95_ms, t.locale)}`}>
          <div className="flex items-baseline justify-between gap-2 text-[13px]">
            <span className="truncate font-medium">{c.category}</span>
            <span className="shrink-0 text-xs text-foreground-muted tabular-nums">
              {formatMs(c.total_ms, t.locale)} · {formatCount((c.total_ms / total) * 100, t.locale)}%
            </span>
          </div>
          <div className="h-2 rounded-full bg-surface-muted">
            <div className="h-2 rounded-full bg-accent" style={{ width: `${(c.total_ms / top) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

const COLUMNS: { key: SortKey; label: string; title?: string }[] = [
  { key: "count", label: msg("Chamadas") },
  { key: "avg_ms", label: msg("Média") },
  { key: "p95_ms", label: "p95" },
  { key: "avg_db_ms", label: msg("Banco (média)") },
  { key: "avg_db_queries", label: msg("SQL por chamada") },
  { key: "server_errors", label: msg("Erros 5xx") },
  { key: "total_ms", label: msg("Tempo total") },
];

function RoutesTable({
  routes,
  selected,
  onSelect,
}: {
  routes: RouteStats[];
  selected: RouteKey | null;
  onSelect: (route: RouteKey) => void;
}) {
  const t = useT();
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "total_ms", desc: true });
  const sorted = [...routes].sort((a, b) => {
    const diff = (a[sort.key] ?? 0) - (b[sort.key] ?? 0);
    return sort.desc ? -diff : diff;
  });
  const cell = "px-3 py-2 text-right tabular-nums whitespace-nowrap";

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead className="border-y border-border bg-surface-muted text-xs text-foreground-muted">
          <tr>
            <th scope="col" className="px-4 py-2 text-left font-medium">{t("Rota")}</th>
            {COLUMNS.map((col) => {
              const active = sort.key === col.key;
              return (
                <th
                  key={col.key}
                  scope="col"
                  aria-sort={active ? (sort.desc ? "descending" : "ascending") : "none"}
                  className="px-3 py-2 text-right font-medium whitespace-nowrap"
                >
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 hover:text-foreground"
                    onClick={() => setSort({ key: col.key, desc: active ? !sort.desc : true })}
                  >
                    {col.key === "p95_ms" ? col.label : t(col.label)}
                    {active && (sort.desc ? <ArrowDown size={12} aria-hidden /> : <ArrowUp size={12} aria-hidden />)}
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const isSelected = selected?.method === r.method && selected.route === r.route;
            const dbShare = r.avg_ms ? Math.min((r.avg_db_ms ?? 0) / r.avg_ms, 1) : 0;
            return (
              <tr
                key={`${r.method} ${r.route}`}
                className={cn(
                  "cursor-pointer border-b border-border last:border-0 hover:bg-surface-hover",
                  isSelected && "bg-accent-soft hover:bg-accent-soft",
                )}
                onClick={() => onSelect({ method: r.method, route: r.route })}
              >
                <td className="px-4 py-2">
                  <button
                    type="button"
                    className="flex min-w-0 flex-col items-start text-left"
                    aria-pressed={isSelected}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelect({ method: r.method, route: r.route });
                    }}
                  >
                    <span className="flex items-center gap-2">
                      <MethodBadge method={r.method} />
                      <span className="font-mono text-xs break-all">{r.route}</span>
                    </span>
                    {r.summary && <span className="text-xs text-foreground-muted">{r.summary}</span>}
                  </button>
                </td>
                <td className={cell}>{formatCount(r.count, t.locale)}</td>
                <td className={cell}>{formatMs(r.avg_ms, t.locale)}</td>
                <td className={cn(cell, "font-medium")}>{formatMs(r.p95_ms, t.locale)}</td>
                <td className={cell}>
                  <span className="inline-flex items-center gap-2">
                    {formatMs(r.avg_db_ms, t.locale)}
                    <span className="h-1.5 w-10 rounded-full bg-surface-muted" title={`${Math.round(dbShare * 100)}%`}>
                      <span className="block h-1.5 rounded-full bg-accent" style={{ width: `${dbShare * 100}%` }} />
                    </span>
                  </span>
                </td>
                <td className={cell}>{formatCount(r.avg_db_queries, t.locale, 1)}</td>
                <td className={cn(cell, r.server_errors && "text-danger")}>{formatCount(r.server_errors, t.locale)}</td>
                <td className={cell}>{formatMs(r.total_ms, t.locale)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function MethodBadge({ method }: { method: string }) {
  return (
    <span className="inline-flex h-5 shrink-0 items-center rounded-sm bg-surface-muted px-1.5 font-mono text-[11px] font-semibold text-foreground">
      {method}
    </span>
  );
}

/** Sugestões a partir dos números da rota (heurísticas simples, para orientar o estudo). */
function suggestions(r: RouteStats, t: Translate): string[] {
  const out: string[] = [];
  const avg = r.avg_ms ?? 0;
  const db = r.avg_db_ms ?? 0;
  if (avg && db / avg >= 0.6) {
    out.push(t("A maior parte do tempo é no banco: reveja as consultas e os índices usados por esta rota."));
  }
  if ((r.avg_db_queries ?? 0) >= 10) {
    out.push(t("Muitos comandos SQL por chamada: pode ser N+1. Carregue os relacionamentos de uma vez (selectinload/join)."));
  }
  if (avg && db / avg < 0.3 && avg >= 300) {
    out.push(t("Pouco tempo no banco e resposta lenta: o custo está no processamento (arquivos, DuckDB, IA). Considere cache ou trabalho em segundo plano."));
  }
  if (r.p50_ms && r.p95_ms && r.p95_ms >= r.p50_ms * 3 && r.count >= 5) {
    out.push(t("O p95 é muito maior que a mediana: há picos. Investigue cache frio, fila de conexões do banco ou chamadas externas."));
  }
  if ((r.avg_response_bytes ?? 0) >= 1024 * 1024) {
    out.push(t("Respostas grandes: pagine os resultados ou envie só os campos necessários."));
  }
  if (r.server_errors) out.push(t("Há erros 5xx nesta rota: veja os logs do servidor nos horários das chamadas."));
  return out;
}

function RouteDetail({
  filter,
  route,
  stats,
  onClose,
}: {
  filter: MetricsFilter;
  route: RouteKey;
  stats: RouteStats | undefined;
  onClose: () => void;
}) {
  const t = useT();
  const [order, setOrder] = useState<"slowest" | "recent">("slowest");
  const timeline = useTimeline(filter, route);
  const logs = useRequestLogs(filter, route, order);
  const tips = stats ? suggestions(stats, t) : [];
  const date = new Intl.DateTimeFormat(intlLocale(t.locale), { dateStyle: "short", timeStyle: "medium" });

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <span className="flex items-center gap-2">
            <MethodBadge method={route.method} />
            <h2 className="font-mono text-sm font-semibold break-all">{route.route}</h2>
          </span>
          {stats?.summary && <p className="text-xs text-foreground-muted">{stats.summary}</p>}
        </div>
        <IconButton aria-label={t("Fechar")} onClick={onClose} icon={<X size={16} strokeWidth={1.75} />} />
      </div>

      {stats && (
        <div className="grid gap-3 text-[13px] sm:grid-cols-4">
          <Figure label="p50" value={formatMs(stats.p50_ms, t.locale)} />
          <Figure label="p99" value={formatMs(stats.p99_ms, t.locale)} />
          <Figure label={t("Máximo")} value={formatMs(stats.max_ms, t.locale)} />
          <Figure label={t("Resposta média")} value={formatBytes(stats.avg_response_bytes, t.locale)} />
        </div>
      )}

      {tips.length > 0 && (
        <ul className="flex flex-col gap-1.5 rounded-md bg-surface-muted p-3 text-[13px]">
          {tips.map((tip) => (
            <li key={tip} className="flex gap-2">
              <Lightbulb size={16} strokeWidth={1.75} aria-hidden className="mt-0.5 shrink-0 text-pending" />
              {tip}
            </li>
          ))}
        </ul>
      )}

      {timeline.data && <TimelineChart points={timeline.data.points} bucketMinutes={timeline.data.bucket_minutes} />}

      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{order === "slowest" ? t("Chamadas mais lentas") : t("Chamadas mais recentes")}</h3>
        <div className="flex gap-1">
          <Button size="sm" variant={order === "slowest" ? "primary" : "ghost"} onClick={() => setOrder("slowest")}>
            {t("Mais lentas")}
          </Button>
          <Button size="sm" variant={order === "recent" ? "primary" : "ghost"} onClick={() => setOrder("recent")}>
            {t("Mais recentes")}
          </Button>
        </div>
      </div>
      {logs.isPending ? (
        <Skeleton className="h-32" />
      ) : logs.isError ? (
        <p role="alert" className="text-sm text-danger">{errorMessage(logs.error, t)}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead className="text-xs text-foreground-muted">
              <tr className="border-b border-border">
                <th scope="col" className="py-1.5 pr-3 text-left font-medium">{t("Quando")}</th>
                <th scope="col" className="py-1.5 pr-3 text-left font-medium">{t("Caminho")}</th>
                <th scope="col" className="py-1.5 pr-3 text-right font-medium">Status</th>
                <th scope="col" className="py-1.5 pr-3 text-right font-medium">{t("Duração")}</th>
                <th scope="col" className="py-1.5 pr-3 text-left font-medium">{t("Banco × resto")}</th>
                <th scope="col" className="py-1.5 text-right font-medium">SQL</th>
              </tr>
            </thead>
            <tbody>
              {logs.data.map((log) => (
                <tr key={log.id} className="border-b border-border last:border-0">
                  <td className="py-1.5 pr-3 whitespace-nowrap text-foreground-muted">{date.format(new Date(log.created_at))}</td>
                  <td className="max-w-72 truncate py-1.5 pr-3 font-mono text-xs" title={log.path}>{log.path}</td>
                  <td className={cn("py-1.5 pr-3 text-right tabular-nums", log.status_code >= 500 && "text-danger")}>{log.status_code}</td>
                  <td className="py-1.5 pr-3 text-right font-medium tabular-nums">{formatMs(log.duration_ms, t.locale)}</td>
                  <td className="py-1.5 pr-3">
                    <SplitBar total={log.duration_ms} db={log.db_ms} label={t("{db} no banco", { db: formatMs(log.db_ms, t.locale) })} />
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{log.db_queries}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function Figure({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-foreground-muted">{label}</span>
      <span className="font-semibold tabular-nums">{value}</span>
    </div>
  );
}

/** Barra com a parte do tempo gasta no banco (cheia) e o resto (clara). */
function SplitBar({ total, db, label }: { total: number; db: number; label: string }) {
  const share = total ? Math.min(db / total, 1) : 0;
  return (
    <span className="flex items-center gap-2" title={label}>
      <span className="flex h-2 w-28 gap-0.5 overflow-hidden rounded-full">
        {share > 0 && <span className="h-2 bg-accent" style={{ width: `${share * 100}%` }} />}
        <span className="h-2 flex-1 bg-surface-muted" />
      </span>
      <span className="text-xs text-foreground-muted tabular-nums">{Math.round(share * 100)}%</span>
    </span>
  );
}
