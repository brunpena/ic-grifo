"use client";

import { FlaskConical, Play } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, FormError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useAnalyses } from "@/lib/analyses";
import { errorMessage } from "@/lib/api";
import { useDocuments, useRules } from "@/lib/documents";
import { intlLocale, useT } from "@/lib/i18n";
import {
  OPERATION_LABELS,
  type SimulationResult,
  useRunSimulation,
  useSimulationOperations,
  useSimulationRuns,
} from "@/lib/performance";
import { DurationHistogram } from "./charts";
import { formatCount, formatMs } from "./format";

export function SimulationPanel() {
  const t = useT();
  const ids = { op: useId(), param: useId(), doc: useId(), path: useId(), n: useId(), c: useId() };
  const operations = useSimulationOperations();
  const run = useRunSimulation();
  const [operation, setOperation] = useState("documents_list");
  const [analysisId, setAnalysisId] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [ruleId, setRuleId] = useState("");
  const [path, setPath] = useState("/api/v1/");
  const [iterations, setIterations] = useState(20);
  const [concurrency, setConcurrency] = useState(1);

  const op = operations.data?.find((o) => o.key === operation);
  const param = op?.param ?? null;
  const analyses = useAnalyses();
  const documents = useDocuments();
  const rules = useRules(documentId || null, param === "rule" && !!documentId);

  const missing =
    (param === "analysis" && !analysisId) ||
    (param === "document" && !documentId) ||
    (param === "rule" && !ruleId) ||
    (operation === "custom" && !path.startsWith("/api/v1/"));

  return (
    <Card className="flex flex-col gap-5 p-5 sm:p-6">
      <div className="flex flex-col gap-1">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <FlaskConical size={16} strokeWidth={1.75} aria-hidden /> {t("Simular operações")}
        </h2>
        <p className="text-[13px] text-foreground-muted">
          {t("Repete uma leitura várias vezes, com chamadas simultâneas, usando a sua sessão. As chamadas passam por toda a API e pelo banco, mas não pela rede do navegador.")}
        </p>
      </div>

      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          run.mutate({
            operation,
            iterations,
            concurrency,
            path: operation === "custom" ? path : null,
            params: {
              analysis_id: param === "analysis" ? analysisId : null,
              document_id: param === "document" ? documentId : null,
              rule_id: param === "rule" ? ruleId : null,
            },
          });
        }}
      >
        {run.error && <FormError>{errorMessage(run.error, t)}</FormError>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("Operação")} htmlFor={ids.op}>
            <Select id={ids.op} value={operation} onChange={(e) => setOperation(e.target.value)}>
              {(operations.data ?? []).map((o) => (
                <option key={o.key} value={o.key}>
                  {t(OPERATION_LABELS[o.key] ?? o.key)}
                </option>
              ))}
              <option value="custom">{t(OPERATION_LABELS.custom)}</option>
            </Select>
          </Field>

          {param === "analysis" && (
            <Field label={t("Análise")} htmlFor={ids.param}>
              <Select id={ids.param} value={analysisId} onChange={(e) => setAnalysisId(e.target.value)}>
                <option value="">{t("Escolha uma análise")}</option>
                {analyses.data?.map((a) => (
                  <option key={a.id} value={a.id}>{a.title}</option>
                ))}
              </Select>
            </Field>
          )}
          {(param === "document" || param === "rule") && (
            <Field label={t("Documento")} htmlFor={ids.doc}>
              <Select
                id={ids.doc}
                value={documentId}
                onChange={(e) => {
                  setDocumentId(e.target.value);
                  setRuleId("");
                }}
              >
                <option value="">{t("Escolha um documento")}</option>
                {documents.data?.map((d) => (
                  <option key={d.id} value={d.id}>{d.title}</option>
                ))}
              </Select>
            </Field>
          )}
          {param === "rule" && (
            <Field label={t("Regra")} htmlFor={ids.param}>
              <Select id={ids.param} value={ruleId} disabled={!documentId} onChange={(e) => setRuleId(e.target.value)}>
                <option value="">{t("Escolha uma regra")}</option>
                {rules.data?.map((r) => (
                  <option key={r.id} value={r.id}>{r.summary || r.excerpt.slice(0, 80)}</option>
                ))}
              </Select>
            </Field>
          )}
          {operation === "custom" && (
            <Field label={t("Caminho")} htmlFor={ids.path} hint={t("Só GET, dentro de /api/v1. Pode ter query string.")}>
              <Input id={ids.path} className="font-mono" value={path} onChange={(e) => setPath(e.target.value)} />
            </Field>
          )}
        </div>
        <div className="grid gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <Field label={t("Repetições")} htmlFor={ids.n} hint={t("De 1 a 500.")}>
            <Input
              id={ids.n}
              type="number"
              min={1}
              max={500}
              value={iterations}
              onChange={(e) => setIterations(Math.min(500, Math.max(1, Number(e.target.value) || 1)))}
            />
          </Field>
          <Field label={t("Simultâneas")} htmlFor={ids.c} hint={t("Chamadas ao mesmo tempo, de 1 a 20.")}>
            <Input
              id={ids.c}
              type="number"
              min={1}
              max={20}
              value={concurrency}
              onChange={(e) => setConcurrency(Math.min(20, Math.max(1, Number(e.target.value) || 1)))}
            />
          </Field>
          <Button type="submit" variant="primary" loading={run.isPending} disabled={missing} className="sm:mb-5">
            <Play size={16} strokeWidth={1.75} aria-hidden /> {t("Executar")}
          </Button>
        </div>
      </form>

      {run.data && <SimulationResultView result={run.data} />}
      <SimulationHistory />
    </Card>
  );
}

function SimulationResultView({ result }: { result: SimulationResult }) {
  const t = useT();
  const rows: { label: string; client: number | null | undefined; server: number | null | undefined }[] = [
    { label: t("Média"), client: result.client.avg_ms, server: result.server?.avg_ms },
    { label: "p50", client: result.client.p50_ms, server: result.server?.p50_ms },
    { label: "p95", client: result.client.p95_ms, server: result.server?.p95_ms },
    { label: "p99", client: result.client.p99_ms, server: result.server?.p99_ms },
    { label: t("Máximo"), client: result.client.max_ms, server: result.server?.max_ms },
  ];
  return (
    <div className="flex flex-col gap-4 rounded-md border border-border p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-mono text-xs break-all">
          {result.method} {result.path}
        </span>
        <span className="text-xs text-foreground-muted">
          {t("{n} chamadas, {c} simultâneas, em {wall} · {rps} req/s", {
            n: result.iterations,
            c: result.concurrency,
            wall: formatMs(result.wall_ms, t.locale),
            rps: formatCount(result.throughput_rps, t.locale, 1),
          })}
        </span>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <table className="text-[13px]">
          <thead className="text-xs text-foreground-muted">
            <tr className="border-b border-border">
              <th scope="col" className="py-1.5 text-left font-medium" />
              <th scope="col" className="py-1.5 text-right font-medium">{t("Quem chamou")}</th>
              <th scope="col" className="py-1.5 text-right font-medium">{t("Servidor")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-b border-border last:border-0">
                <th scope="row" className="py-1.5 text-left font-medium">{r.label}</th>
                <td className="py-1.5 text-right tabular-nums">{formatMs(r.client, t.locale)}</td>
                <td className="py-1.5 text-right tabular-nums">{formatMs(r.server, t.locale)}</td>
              </tr>
            ))}
            <tr>
              <th scope="row" className="py-1.5 text-left font-medium">{t("Banco (média)")}</th>
              <td className="py-1.5 text-right text-foreground-subtle">—</td>
              <td className="py-1.5 text-right tabular-nums">
                {formatMs(result.server?.avg_db_ms, t.locale)} · {formatCount(result.server?.avg_db_queries, t.locale, 1)} SQL
              </td>
            </tr>
          </tbody>
        </table>
        <div className="flex flex-col gap-2">
          <span className="text-xs text-foreground-muted">{t("Distribuição das durações")}</span>
          <DurationHistogram durations={result.durations_ms} />
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(result.status_counts).map(([status, count]) => (
              <span
                key={status}
                className={
                  status.startsWith("2") ? "rounded-sm bg-success-soft px-2 py-0.5 text-success" : "rounded-sm bg-danger-soft px-2 py-0.5 text-danger"
                }
              >
                {status}: {count}
              </span>
            ))}
          </div>
        </div>
      </div>
      <p className="text-xs text-foreground-subtle">
        {t("A diferença entre “quem chamou” e “servidor” é o tempo esperando vaga: com muitas simultâneas, as chamadas fazem fila.")}
      </p>
    </div>
  );
}

function SimulationHistory() {
  const t = useT();
  const runs = useSimulationRuns();
  if (!runs.data?.length) return null;
  const date = new Intl.DateTimeFormat(intlLocale(t.locale), { dateStyle: "short", timeStyle: "short" });
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">{t("Simulações anteriores")}</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead className="text-xs text-foreground-muted">
            <tr className="border-b border-border">
              <th scope="col" className="py-1.5 pr-3 text-left font-medium">{t("Quando")}</th>
              <th scope="col" className="py-1.5 pr-3 text-left font-medium">{t("Rota")}</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">{t("Chamadas")}</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">{t("Média")}</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">p95</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">{t("Banco (média)")}</th>
              <th scope="col" className="py-1.5 text-right font-medium">{t("Erros 5xx")}</th>
            </tr>
          </thead>
          <tbody>
            {runs.data.map((r) => (
              <tr key={r.simulation_id} className="border-b border-border last:border-0">
                <td className="py-1.5 pr-3 whitespace-nowrap text-foreground-muted">{date.format(new Date(r.started_at))}</td>
                <td className="py-1.5 pr-3 font-mono text-xs break-all">
                  {r.method} {r.route}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{r.count}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatMs(r.avg_ms, t.locale)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatMs(r.p95_ms, t.locale)}</td>
                <td className="py-1.5 pr-3 text-right tabular-nums">{formatMs(r.avg_db_ms, t.locale)}</td>
                <td className={r.server_errors ? "py-1.5 text-right text-danger" : "py-1.5 text-right"}>{r.server_errors}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
