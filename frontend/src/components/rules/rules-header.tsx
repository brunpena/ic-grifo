"use client";

import { Info } from "lucide-react";
import { ProgressBar } from "@/components/ui/progress-bar";
import { RuleTypeSelect } from "@/components/ui/rule-type-select";
import { Select } from "@/components/ui/select";
import { RULE_STATUS, type RuleStatus, type RuleType } from "@/lib/design/tokens";
import { cn } from "@/lib/utils";

const STATUSES = Object.keys(RULE_STATUS) as RuleStatus[];

type RulesHeaderProps = {
  validated: number;
  total: number;
  typeFilter: RuleType | null;
  onTypeFilterChange: (type: RuleType | null) => void;
  statusFilter: RuleStatus | null;
  onStatusFilterChange: (status: RuleStatus | null) => void;
  className?: string;
};

/** Topo da tabela: progresso de validação e filtros por tipo e situação. */
export function RulesHeader({
  validated,
  total,
  typeFilter,
  onTypeFilterChange,
  statusFilter,
  onStatusFilterChange,
  className,
}: RulesHeaderProps) {
  return (
    <div className={cn("flex shrink-0 flex-col gap-3 border-b border-border bg-surface p-3", className)}>
      <div className="flex flex-col gap-1.5">
        <p className="text-[13px] text-foreground-muted tabular-nums">
          <span className="font-medium text-foreground">{validated}</span> de {total} regras validadas
        </p>
        <ProgressBar value={validated} max={total} label="Regras validadas" />
      </div>
      <div className="flex flex-wrap gap-2">
        <RuleTypeSelect
          allowAll
          value={typeFilter}
          onChange={onTypeFilterChange}
          aria-label="Filtrar por tipo"
          className="w-44"
        />
        <Select
          aria-label="Filtrar por situação"
          value={statusFilter ?? ""}
          onChange={(e) => onStatusFilterChange((e.target.value || null) as RuleStatus | null)}
          className="w-44"
        >
          <option value="">Todas as situações</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {RULE_STATUS[s].label}
            </option>
          ))}
        </Select>
      </div>
    </div>
  );
}

/** Aviso de que a tabela mostra só as regras citadas numa resposta. */
export function RulesFilterNotice({
  count,
  onShowAll,
  className,
}: {
  count: number;
  onShowAll: () => void;
  className?: string;
}) {
  return (
    <div
      role="status"
      className={cn(
        "flex shrink-0 items-center gap-2 border-b border-border bg-surface px-3 py-2 text-[13px] text-foreground-muted",
        className,
      )}
    >
      <Info size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-foreground-subtle" />
      <span>
        Mostrando {count} {count === 1 ? "regra" : "regras"} da resposta
      </span>
      <span aria-hidden>·</span>
      <button
        type="button"
        onClick={onShowAll}
        className="rounded-sm text-accent underline-offset-2 hover:underline"
      >
        mostrar todas as regras
      </button>
    </div>
  );
}
