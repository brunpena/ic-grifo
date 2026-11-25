"use client";

import { AlertTriangle, Info } from "lucide-react";
import type { ReactNode } from "react";
import { ProgressBar } from "@/components/ui/progress-bar";
import { RuleTypeSelect } from "@/components/ui/rule-type-select";
import { Select } from "@/components/ui/select";
import { RULE_STATUS, type RuleStatus, type RuleType } from "@/lib/design/tokens";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const STATUSES = Object.keys(RULE_STATUS) as RuleStatus[];

export type RuleCategoryFilter = "csv" | "geral" | null;

const CATEGORY_TABS: { value: RuleCategoryFilter; label: string }[] = [
  { value: null, label: "Todas" },
  { value: "csv", label: "Verificáveis no CSV" },
  { value: "geral", label: "Gerais" },
];

type RulesHeaderProps = {
  validated: number;
  total: number;
  typeFilter: RuleType | null;
  onTypeFilterChange: (type: RuleType | null) => void;
  statusFilter: RuleStatus | null;
  onStatusFilterChange: (status: RuleStatus | null) => void;
  /** Botões à direita dos filtros (ex.: gerar buscas). */
  actions?: ReactNode;
  /** Aviso do processamento (ex.: validação em andamento). */
  notice?: string | null;
  /**
   * Separação do banco de regras. Com ela, o topo mostra as categorias no lugar do
   * progresso de validação (toda regra já entra aprovada).
   */
  categories?: {
    value: RuleCategoryFilter;
    onChange: (value: RuleCategoryFilter) => void;
    counts: { csv: number; geral: number };
  };
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
  actions,
  notice,
  categories,
  className,
}: RulesHeaderProps) {
  const t = useT();
  return (
    <div className={cn("flex shrink-0 flex-col gap-3 border-b border-border bg-surface p-3", className)}>
      {categories ? (
        <div role="tablist" aria-label="Categoria das regras" className="flex flex-wrap gap-1">
          {CATEGORY_TABS.map((tab) => {
            const count =
              tab.value === null ? categories.counts.csv + categories.counts.geral : categories.counts[tab.value];
            const active = categories.value === tab.value;
            return (
              <button
                key={tab.label}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => categories.onChange(tab.value)}
                className={cn(
                  "inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-medium transition-colors duration-150 ease-out",
                  active ? "bg-accent-soft text-accent" : "text-foreground-muted hover:bg-surface-hover hover:text-foreground",
                )}
              >
                {tab.label}
                <span className="font-mono text-[11px] tabular-nums">{count}</span>
              </button>
            );
          })}
        </div>
      ) : (
      <div className="flex flex-col gap-1.5">
        <p className="text-[13px] text-foreground-muted tabular-nums">
          <span className="font-medium text-foreground">{t.number(validated)}</span>{" "}
          {t.plural(total, "de {n} regra validada", "de {n} regras validadas")}
        </p>
        <ProgressBar value={validated} max={total} label={t("Regras validadas")} />
      </div>
      )}
      <div className="flex flex-wrap gap-2">
        <RuleTypeSelect
          allowAll
          value={typeFilter}
          onChange={onTypeFilterChange}
          aria-label={t("Filtrar por tipo")}
          className="w-44"
        />
        <Select
          aria-label={t("Filtrar por situação")}
          value={statusFilter ?? ""}
          onChange={(e) => onStatusFilterChange((e.target.value || null) as RuleStatus | null)}
          className="w-44"
        >
          <option value="">{t("Todas as situações")}</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(RULE_STATUS[s].label)}
            </option>
          ))}
        </Select>
        {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
      </div>
      {notice && (
        <p role="status" className="flex items-start gap-2 rounded-md bg-pending-soft px-2.5 py-2 text-xs text-foreground-muted">
          <AlertTriangle size={14} strokeWidth={1.75} aria-hidden className="mt-px shrink-0 text-rule-prazo" />
          {notice}
        </p>
      )}
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
  const t = useT();
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
        {t.plural(count, "Mostrando {n} regra da resposta", "Mostrando {n} regras da resposta")}
      </span>
      <span aria-hidden>·</span>
      <button
        type="button"
        onClick={onShowAll}
        className="rounded-sm text-accent underline-offset-2 hover:underline"
      >
        {t("mostrar todas as regras")}
      </button>
    </div>
  );
}
