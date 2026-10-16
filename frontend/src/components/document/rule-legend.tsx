"use client";

import { RuleTypeDot } from "@/components/ui/badge";
import { RULE_TYPES, type RuleType } from "@/lib/design/tokens";
import { cn } from "@/lib/utils";

const TYPES = Object.keys(RULE_TYPES) as RuleType[];

type RuleLegendProps = {
  /** Tipo usado como filtro da tabela, ou `null` para nenhum. */
  active: RuleType | null;
  /** Clicar no tipo ativo remove o filtro. */
  onChange: (type: RuleType | null) => void;
  className?: string;
};

export function RuleLegend({ active, onChange, className }: RuleLegendProps) {
  return (
    <div
      role="group"
      aria-label="Legenda dos tipos de regra. Clique para filtrar a tabela"
      className={cn(
        "flex h-9 shrink-0 items-center gap-1 overflow-x-auto border-b border-border bg-surface px-2",
        className,
      )}
    >
      {TYPES.map((type) => (
        <button
          key={type}
          type="button"
          aria-pressed={active === type}
          onClick={() => onChange(active === type ? null : type)}
          className={cn(
            "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-sm px-2 text-xs text-foreground-muted",
            "transition-colors duration-150 ease-out hover:bg-surface-hover hover:text-foreground",
            active === type && "bg-accent-soft text-foreground hover:bg-accent-soft",
          )}
        >
          <RuleTypeDot type={type} />
          {RULE_TYPES[type].label}
        </button>
      ))}
    </div>
  );
}
