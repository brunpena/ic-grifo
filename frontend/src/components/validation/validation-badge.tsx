"use client";

import { Tooltip } from "@/components/ui/tooltip";
import { type RuleValidation, type ValidationStatus, VALIDATION_LABELS } from "@/lib/validation";
import { cn } from "@/lib/utils";

const COLOR: Record<ValidationStatus, string> = {
  conforme: "bg-accent-soft text-accent", violacao: "bg-danger-soft text-danger",
  inconclusiva: "bg-surface-muted text-foreground-muted",
  nao_aplicavel: "bg-surface-muted text-foreground-subtle",
  erro: "bg-danger-soft text-danger", desatualizada: "bg-surface-muted text-foreground-muted",
  ignorada: "bg-surface-muted text-foreground-subtle",
};

export function ValidationBadge({ validation }: { validation?: RuleValidation | null }) {
  if (!validation) return <span className="text-xs text-foreground-subtle">Não avaliada</span>;
  const detail = [validation.explanation, ...(validation.missing_data ?? [])].join(" ");
  return (
    <Tooltip content={detail}>
      <span className={cn("inline-flex rounded-sm px-2 py-1 text-xs font-medium", COLOR[validation.status])}>
        {VALIDATION_LABELS[validation.status]}
      </span>
    </Tooltip>
  );
}

export function ValidationSummary({ rules }: { rules: { validation?: RuleValidation | null }[] }) {
  const count = (status: ValidationStatus) => rules.filter((r) => r.validation?.status === status).length;
  const unresolved = rules.filter((r) => !r.validation || ["erro", "desatualizada"].includes(r.validation.status)).length;
  return (
    <div className="border-b border-border px-3 py-3" aria-label="Validação geral das regras" aria-live="polite">
      <div className="mb-2 flex items-center justify-between gap-2 text-xs">
        <span className="font-medium">Validação nas bases</span>
        <span className="text-foreground-subtle">{rules.length} regras · {unresolved} por avaliar</span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div><strong className="block text-base font-semibold text-accent tabular-nums">{count("conforme")}</strong>Conformes</div>
        <div><strong className="block text-base font-semibold text-danger tabular-nums">{count("violacao")}</strong>Com violações</div>
        <div><strong className="block text-base font-semibold tabular-nums">{count("inconclusiva")}</strong>Inconclusivas</div>
      </div>
      {(count("nao_aplicavel") > 0 || count("ignorada") > 0) && (
        <p className="mt-2 text-xs text-foreground-subtle">{count("nao_aplicavel")} sem registros aplicáveis · {count("ignorada")} desconsideradas na revisão</p>
      )}
    </div>
  );
}
