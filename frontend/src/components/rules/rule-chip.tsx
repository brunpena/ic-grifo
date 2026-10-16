"use client";

import { RuleTypeDot } from "@/components/ui/badge";
import { RULE_TYPES, type RuleType } from "@/lib/design/tokens";
import { cn } from "@/lib/utils";

type RuleChipProps = {
  type: RuleType;
  summary: string;
  /** Hover e foco destacam a regra no documento. */
  onHighlight?: (highlighted: boolean) => void;
  /** Clique navega até a regra. */
  onClick?: () => void;
  className?: string;
};

/** Regra citada numa resposta: bolinha da cor do tipo e o resumo curto. */
export function RuleChip({ type, summary, onHighlight, onClick, className }: RuleChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      onPointerEnter={() => onHighlight?.(true)}
      onPointerLeave={() => onHighlight?.(false)}
      onFocus={() => onHighlight?.(true)}
      onBlur={() => onHighlight?.(false)}
      className={cn(
        "inline-flex h-7 max-w-full items-center gap-1.5 rounded-md border border-border bg-surface px-2 text-xs text-foreground",
        "transition-colors duration-150 ease-out hover:border-border-strong hover:bg-surface-hover",
        className,
      )}
    >
      <RuleTypeDot type={type} />
      <span className="sr-only">{RULE_TYPES[type].label}: </span>
      <span className="truncate">{summary}</span>
    </button>
  );
}
