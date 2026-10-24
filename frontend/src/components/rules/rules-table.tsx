"use client";

import { Check, FileSearch, RotateCcw, X } from "lucide-react";
import type { ReactNode } from "react";
import { RuleStatusBadge, RuleTypeBadge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { IconButton } from "@/components/ui/icon-button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { RULE_TYPES, type RuleStatus } from "@/lib/design/tokens";
import { cn } from "@/lib/utils";
import { QueryBadge } from "@/components/queries/query-badge";
import type { RuleView } from "./types";

type RulesTableProps = {
  rules: RuleView[];
  selectedId?: string | null;
  onSelect?: (rule: RuleView) => void;
  /** Hover na linha destaca o grifo no documento. */
  onHover?: (rule: RuleView | null) => void;
  onSetStatus?: (rule: RuleView, status: RuleStatus) => void;
  /** Mostra a coluna da busca nas bases (análises com CSV) e abre o editor. */
  onEditQuery?: (rule: RuleView) => void;
  /** Regras com uma mudança de situação em andamento. */
  pendingIds?: ReadonlySet<string>;
  loading?: boolean;
  /** Conteúdo quando não há regras (o padrão serve para filtros sem resultado). */
  empty?: ReactNode;
  className?: string;
};

const ACTIONS: { status: RuleStatus; label: string; icon: ReactNode }[] = [
  { status: "validada", label: "Validar regra", icon: <Check size={16} strokeWidth={1.75} aria-hidden /> },
  { status: "rejeitada", label: "Rejeitar regra", icon: <X size={16} strokeWidth={1.75} aria-hidden /> },
  {
    status: "pendente",
    label: "Voltar para pendente",
    icon: <RotateCcw size={16} strokeWidth={1.75} aria-hidden />,
  },
];

const HEAD = "h-9 px-3 text-left text-xs font-medium whitespace-nowrap text-foreground-muted";
const CELL = "h-11 border-b border-border px-3";
const TRECHO = "hidden @2xl:table-cell";
const PAGINA = "hidden @xl:table-cell";

export function RulesTable({
  rules,
  selectedId,
  onSelect,
  onHover,
  onSetStatus,
  onEditQuery,
  pendingIds,
  loading,
  empty,
  className,
}: RulesTableProps) {
  const showQuery = !!onEditQuery;
  return (
    <div className={cn("@container min-h-0 overflow-auto", className)} aria-busy={loading || undefined}>
      {/* Em painéis estreitos, as colunas Trecho e Página saem (o trecho fica no grifo). */}
      <table className={cn("w-full min-w-[400px] table-fixed border-separate border-spacing-0 text-sm @2xl:min-w-[640px]", showQuery && "min-w-[480px] @2xl:min-w-[760px]")}>
        <colgroup>
          <col className="w-32" />
          <col className="hidden @2xl:table-column" />
          <col />
          <col className="hidden w-16 @xl:table-column" />
          <col className="w-32" />
          {showQuery && <col className="w-24 @2xl:w-36" />}
          <col className={showQuery ? "w-20" : "w-24"} />
        </colgroup>
        <thead className="sticky top-0 z-10 bg-surface-muted">
          <tr>
            <th scope="col" className={HEAD}>Tipo</th>
            <th scope="col" className={cn(HEAD, TRECHO)}>Trecho</th>
            <th scope="col" className={HEAD}>Resumo</th>
            <th scope="col" className={cn(HEAD, PAGINA)}>Página</th>
            <th scope="col" className={HEAD}>Situação</th>
            {showQuery && <th scope="col" className={HEAD}>Busca na base</th>}
            <th scope="col" className={HEAD}>
              <span className="sr-only">Ações</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: 8 }, (_, i) => (
                <tr key={i} aria-hidden>
                  <td className={CELL}><Skeleton className="h-6 w-24" /></td>
                  <td className={cn(CELL, TRECHO)}><Skeleton className="h-3 w-full" /></td>
                  <td className={CELL}><Skeleton className="h-3 w-4/5" /></td>
                  <td className={cn(CELL, PAGINA)}><Skeleton className="h-3 w-6" /></td>
                  <td className={CELL}><Skeleton className="h-6 w-24" /></td>
                  {showQuery && <td className={CELL}><Skeleton className="h-6 w-24" /></td>}
                  <td className={CELL} />
                </tr>
              ))
            : rules.map((rule) => (
                <RuleRow
                  key={rule.id}
                  rule={rule}
                  selected={rule.id === selectedId}
                  busy={pendingIds?.has(rule.id) ?? false}
                  onSelect={onSelect}
                  onHover={onHover}
                  onSetStatus={onSetStatus}
                  onEditQuery={onEditQuery}
                />
              ))}
        </tbody>
      </table>
      {!loading && rules.length === 0 && (
        empty ?? (
          <EmptyState
            icon={FileSearch}
            title="Nenhuma regra encontrada"
            description="Ajuste os filtros ou selecione um trecho do documento para criar uma regra."
          />
        )
      )}
    </div>
  );
}

function RuleRow({
  rule,
  selected,
  busy,
  onSelect,
  onHover,
  onSetStatus,
  onEditQuery,
}: {
  rule: RuleView;
  selected: boolean;
  busy: boolean;
} & Pick<RulesTableProps, "onSelect" | "onHover" | "onSetStatus" | "onEditQuery">) {
  return (
    <tr
      tabIndex={0}
      aria-current={selected || undefined}
      onClick={() => onSelect?.(rule)}
      onKeyDown={(e) => {
        if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onSelect?.(rule);
        }
      }}
      onPointerEnter={() => onHover?.(rule)}
      onPointerLeave={() => onHover?.(null)}
      className={cn(
        "group cursor-pointer outline-offset-[-2px] transition-colors duration-150 ease-out",
        selected ? "bg-accent-soft" : "hover:bg-surface-hover",
      )}
    >
      <td
        className={CELL}
        // Barra de 3 px à esquerda, na cor do tipo, marca a linha selecionada.
        style={selected ? { boxShadow: `inset 3px 0 0 ${RULE_TYPES[rule.type].cssVar}` } : undefined}
      >
        <RuleTypeBadge type={rule.type} />
      </td>
      <td className={cn(CELL, TRECHO)}>
        <Tooltip content={rule.excerpt} className="flex max-w-full min-w-0">
          <span className="truncate font-mono text-xs text-foreground-muted">{rule.excerpt}</span>
        </Tooltip>
      </td>
      <td className={CELL} title={rule.summary}>
        {/* Em painel estreito, o resumo usa até duas linhas em vez de virar "Gar…". */}
        <span className="line-clamp-2 leading-snug">{rule.summary}</span>
      </td>
      <td className={cn(CELL, PAGINA, "font-mono text-xs text-foreground-muted tabular-nums")}>{rule.page ?? "—"}</td>
      <td className={CELL}>
        <RuleStatusBadge status={rule.status} />
      </td>
      {onEditQuery && (
        <td className={CELL}>
          <QueryBadge query={rule.query} onClick={() => onEditQuery(rule)} />
        </td>
      )}
      <td className={CELL}>
        {/* Aparecem no hover e no foco; em telas de toque ficam sempre visíveis. */}
        <div
          className={cn(
            "flex justify-end gap-0.5 transition-opacity duration-150 ease-out",
            !selected && "[@media(hover:hover)]:opacity-0",
            "group-hover:opacity-100 group-focus-within:opacity-100",
          )}
        >
          {ACTIONS.filter((a) => a.status !== rule.status).map((action) => (
            <IconButton
              key={action.status}
              aria-label={action.label}
              icon={action.icon}
              loading={busy}
              onClick={(e) => {
                e.stopPropagation();
                onSetStatus?.(rule, action.status);
              }}
            />
          ))}
        </div>
      </td>
    </tr>
  );
}
