"use client";

import { AlertTriangle, BookText, Database, Plus } from "lucide-react";
import type { MouseEvent } from "react";
import { Tooltip } from "@/components/ui/tooltip";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { RuleQuerySummary } from "@/components/rules/types";

const BADGE =
  "inline-flex h-6 max-w-full items-center gap-1.5 rounded-sm px-2 text-xs font-medium whitespace-nowrap transition-colors duration-150 ease-out";

/** Situação da busca da regra; clicar abre o editor. */
export function QueryBadge({
  query,
  general,
  onClick,
  className,
}: {
  query: RuleQuerySummary | null | undefined;
  /** Regra geral: registrada sem busca porque não se aplica às bases CSV. */
  general?: boolean;
  onClick?: () => void;
  className?: string;
}) {
  const t = useT();
  const handle = (e: MouseEvent) => {
    e.stopPropagation();
    onClick?.();
  };
  if (!query && general) {
    return (
      <Tooltip content="Regra geral: não se aplica às bases CSV. Clique para criar uma busca.">
        <button
          type="button"
          onClick={handle}
          className={cn(BADGE, "bg-surface-muted text-foreground-muted hover:bg-surface-hover hover:text-foreground", className)}
        >
          <BookText size={14} strokeWidth={1.75} aria-hidden />
          Geral
        </button>
      </Tooltip>
    );
  }
  if (!query) {
    return (
      <button
        type="button"
        onClick={handle}
        className={cn(BADGE, "text-foreground-subtle hover:bg-surface-hover hover:text-foreground", className)}
      >
        <Plus size={14} strokeWidth={1.75} aria-hidden />
        {t("Criar")}<span className="hidden @2xl:inline"> {t("busca")}</span>
      </button>
    );
  }
  if (query.state === "erro") {
    return (
      <Tooltip content={query.error ?? t("Erro na busca")}>
        <button type="button" onClick={handle} className={cn(BADGE, "bg-danger-soft text-danger", className)}>
          <AlertTriangle size={14} strokeWidth={1.75} aria-hidden />
          {t("Corrigir")}<span className="hidden @2xl:inline"> {t("busca")}</span>
          <span className="sr-only">: {query.error}</span>
        </button>
      </Tooltip>
    );
  }
  const count = query.match_count ?? 0;
  return (
    <Tooltip content={`${query.dataset_name ?? t("Base")}: ${query.description}`}>
      <button
        type="button"
        onClick={handle}
        className={cn(BADGE, "bg-accent-soft text-accent hover:bg-accent-soft/70", className)}
      >
        <Database size={14} strokeWidth={1.75} aria-hidden />
        {query.state === "pendente" ? (
          t("Pronta")
        ) : (
          <span className="tabular-nums">
            {t.number(count)}
            {/* Em painel estreito fica só o número (o leitor de tela ouve o texto completo). */}
            <span className="hidden @2xl:inline"> {count === 1 ? t("registro") : t("registros")}</span>
            <span className="sr-only @2xl:hidden"> {count === 1 ? t("registro") : t("registros")}</span>
          </span>
        )}
        <span className="sr-only">. {query.description}. {t("Editar busca")}</span>
      </button>
    </Tooltip>
  );
}
