"use client";

import { AlertTriangle, Database, Plus } from "lucide-react";
import type { MouseEvent } from "react";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { RuleQuerySummary } from "@/components/rules/types";

const BADGE =
  "inline-flex h-6 max-w-full items-center gap-1.5 rounded-sm px-2 text-xs font-medium whitespace-nowrap transition-colors duration-150 ease-out";

/** Situação da busca da regra; clicar abre o editor. */
export function QueryBadge({
  query,
  onClick,
  className,
}: {
  query: RuleQuerySummary | null | undefined;
  onClick?: () => void;
  className?: string;
}) {
  const handle = (e: MouseEvent) => {
    e.stopPropagation();
    onClick?.();
  };
  if (!query) {
    return (
      <button
        type="button"
        onClick={handle}
        className={cn(BADGE, "text-foreground-subtle hover:bg-surface-hover hover:text-foreground", className)}
      >
        <Plus size={14} strokeWidth={1.75} aria-hidden />
        Criar busca
      </button>
    );
  }
  if (query.state === "erro") {
    return (
      <Tooltip content={query.error ?? "Erro na busca"}>
        <button type="button" onClick={handle} className={cn(BADGE, "bg-danger-soft text-danger", className)}>
          <AlertTriangle size={14} strokeWidth={1.75} aria-hidden />
          Corrigir busca
          <span className="sr-only">: {query.error}</span>
        </button>
      </Tooltip>
    );
  }
  const count = query.match_count ?? 0;
  return (
    <Tooltip content={`${query.dataset_name ?? "Base"}: ${query.description}`}>
      <button
        type="button"
        onClick={handle}
        className={cn(BADGE, "bg-accent-soft text-accent hover:bg-accent-soft/70", className)}
      >
        <Database size={14} strokeWidth={1.75} aria-hidden />
        <span className="tabular-nums">
          {query.state === "pendente" ? "Pendente" : `${count.toLocaleString("pt-BR")} ${count === 1 ? "registro" : "registros"}`}
        </span>
        <span className="sr-only">. {query.description}. Editar busca</span>
      </button>
    </Tooltip>
  );
}
