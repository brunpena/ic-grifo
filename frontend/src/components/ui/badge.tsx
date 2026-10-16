import { CircleCheck, CircleDashed, CircleX, type LucideIcon } from "lucide-react";
import { RULE_STATUS, RULE_TYPES, type RuleStatus, type RuleType } from "@/lib/design/tokens";
import { cn } from "@/lib/utils";

const BADGE =
  "inline-flex h-6 items-center gap-1.5 rounded-sm px-2 text-xs font-medium whitespace-nowrap";

/** Bolinha na cor do tipo. Decorativa: sempre acompanhe com o nome do tipo. */
export function RuleTypeDot({ type, className }: { type: RuleType; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block size-2 shrink-0 rounded-full", className)}
      style={{ backgroundColor: RULE_TYPES[type].cssVar }}
    />
  );
}

export function RuleTypeBadge({ type, className }: { type: RuleType; className?: string }) {
  return (
    <span className={cn(BADGE, "bg-surface-muted text-foreground", className)}>
      <RuleTypeDot type={type} />
      {RULE_TYPES[type].label}
    </span>
  );
}

const STATUS_STYLE: Record<RuleStatus, { Icon: LucideIcon; className: string }> = {
  pendente: { Icon: CircleDashed, className: "bg-pending-soft text-pending" },
  validada: { Icon: CircleCheck, className: "bg-success-soft text-success" },
  rejeitada: { Icon: CircleX, className: "bg-danger-soft text-danger" },
};

/** O ícone é obrigatório para não confundir "validada" com o verde do tipo obrigação. */
export function RuleStatusBadge({ status, className }: { status: RuleStatus; className?: string }) {
  const { Icon, className: tone } = STATUS_STYLE[status];
  return (
    <span className={cn(BADGE, tone, className)}>
      <Icon size={14} strokeWidth={1.75} aria-hidden />
      {RULE_STATUS[status].label}
    </span>
  );
}
