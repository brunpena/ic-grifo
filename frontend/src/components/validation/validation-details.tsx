"use client";

import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { Select } from "@/components/ui/select";
import { errorMessage } from "@/lib/api";
import type { Rule } from "@/lib/documents";
import { type RecordVerdict, useValidationRecords, VALIDATION_LABELS } from "@/lib/validation";
import { ValidationBadge } from "./validation-badge";

export function ValidationDetails({ rule, onBack }: { rule: Rule; onBack: () => void }) {
  const validation = rule.validation!;
  const available = validation.datasets ?? [];
  const missing = validation.missing_data ?? [];
  const [datasetId, setDatasetId] = useState<string | null>(available[0]?.dataset_id ?? null);
  const [filter, setFilter] = useState<RecordVerdict | "">("");
  const [offset, setOffset] = useState(0);
  const stale = ["desatualizada", "ignorada", "erro"].includes(validation.status);
  const records = useValidationRecords(rule.id, stale ? null : datasetId, offset, filter);
  const data = records.data;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 items-start gap-2 border-b border-border px-3 py-3">
        <IconButton aria-label="Ver todas as regras" icon={<ArrowLeft size={16} aria-hidden />} onClick={onBack} />
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <p className="text-[13px] font-medium">{rule.summary}</p>
          <div><ValidationBadge validation={validation} /></div>
          <p className="text-xs text-foreground-muted">{validation.explanation}</p>
          {missing.length > 0 && (
            <ul className="list-disc space-y-1 pl-4 text-xs text-foreground-muted">
              {missing.map((text, index) => <li key={index}>{text}</li>)}
            </ul>
          )}
          <p className="text-xs text-foreground-subtle">
            {validation.passed_count.toLocaleString("pt-BR")} conformes · {validation.failed_count.toLocaleString("pt-BR")} violações · {validation.unknown_count.toLocaleString("pt-BR")} inconclusivos
          </p>
          <p className="text-[11px] text-foreground-subtle">Verificação em {new Date(validation.checked_at).toLocaleString("pt-BR")}. A revisão humana da regra é independente deste resultado.</p>
        </div>
      </div>
      {available.length > 0 && !stale && (
        <>
          <div className="flex shrink-0 flex-wrap gap-2 border-b border-border p-2">
            <Select aria-label="Base verificada" value={datasetId ?? ""} onChange={(e) => { setDatasetId(e.target.value); setOffset(0); }} className="min-w-32 flex-1">
              {available.map((d) => <option key={d.dataset_id} value={d.dataset_id}>{d.dataset_name}</option>)}
            </Select>
            <Select aria-label="Resultado do registro" value={filter} onChange={(e) => { setFilter(e.target.value as RecordVerdict | ""); setOffset(0); }}>
              <option value="">Todos os resultados</option>
              <option value="conforme">Conformes</option>
              <option value="violacao">Violações</option>
              <option value="inconclusiva">Inconclusivos</option>
            </Select>
          </div>
          {records.isError ? (
            <div role="alert" className="p-4 text-sm text-danger">
              <p>{errorMessage(records.error)}</p>
              <Button size="sm" onClick={() => void records.refetch()} className="mt-2">Tentar novamente</Button>
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-auto" aria-busy={records.isFetching}>
              {!data ? <p role="status" className="p-4 text-sm text-foreground-muted">Carregando registros…</p> : data.total === 0 ? (
                <p className="p-4 text-sm text-foreground-muted">Nenhum registro para este resultado. Isso não comprova o cumprimento da regra.</p>
              ) : (
                <table className="border-separate border-spacing-0 text-left text-[13px]">
                  <thead className="sticky top-0 z-10 bg-surface-muted">
                    <tr>{["Linha", "Resultado", "Evidência", ...data.columns].map((c, i) => (
                      <th key={i} className="border-b border-border px-3 py-2 text-xs font-medium whitespace-nowrap">{c}</th>
                    ))}</tr>
                  </thead>
                  <tbody className={records.isPlaceholderData ? "opacity-60" : ""}>
                    {data.rows.map((row) => (
                      <tr key={row.index} className="hover:bg-surface-hover">
                        <td className="border-b border-border px-3 py-2 font-mono text-xs">{row.index + 1}</td>
                        <td className="border-b border-border px-3 py-2 whitespace-nowrap">{VALIDATION_LABELS[row.verdict]}</td>
                        <td className="min-w-64 border-b border-border px-3 py-2 text-xs text-foreground-muted">{row.explanation}</td>
                        {row.values.map((value, i) => <td key={i} className="max-w-64 truncate border-b border-border px-3 py-2 whitespace-nowrap" title={value ?? undefined}>{value ?? "—"}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
          {data && (
            <div className="flex shrink-0 items-center gap-2 border-t border-border px-3 py-2 text-xs text-foreground-muted">
              <span aria-live="polite">{data.total === 0 ? 0 : offset + 1}–{Math.min(offset + 100, data.total)} de {data.total.toLocaleString("pt-BR")}</span>
              <div className="ml-auto flex">
                <IconButton aria-label="Página anterior" icon={<ChevronLeft size={16} aria-hidden />} disabled={offset === 0 || records.isPlaceholderData} onClick={() => setOffset(Math.max(0, offset - 100))} />
                <IconButton aria-label="Próxima página" icon={<ChevronRight size={16} aria-hidden />} disabled={offset + 100 >= data.total || records.isPlaceholderData} onClick={() => setOffset(offset + 100)} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
