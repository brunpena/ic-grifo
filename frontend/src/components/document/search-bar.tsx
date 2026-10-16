"use client";

import { ChevronDown, ChevronUp, Search, X } from "lucide-react";
import { IconButton } from "@/components/ui/icon-button";
import { cn } from "@/lib/utils";

type SearchBarProps = {
  query: string;
  onQueryChange: (query: string) => void;
  /** Índice da ocorrência atual, começando em 0. */
  current: number;
  total: number;
  onPrevious: () => void;
  onNext: () => void;
  onClose: () => void;
  className?: string;
};

/**
 * Barra de busca no documento (Ctrl+F). Posicione no canto superior direito do
 * workspace. Enter vai para a próxima, Shift+Enter para a anterior, Esc fecha.
 */
export function SearchBar({
  query,
  onQueryChange,
  current,
  total,
  onPrevious,
  onNext,
  onClose,
  className,
}: SearchBarProps) {
  const hasQuery = query.trim().length > 0;
  const noResults = hasQuery && total === 0;

  return (
    <div
      role="search"
      className={cn(
        "flex w-80 max-w-[calc(100vw-32px)] items-center gap-1 rounded-lg border border-border bg-surface p-1 shadow-md",
        "transition-colors duration-150 ease-out focus-within:border-ring animate-enter",
        className,
      )}
    >
      <Search size={16} strokeWidth={1.75} aria-hidden className="ml-1.5 shrink-0 text-foreground-subtle" />
      <input
        type="search"
        autoFocus
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            if (e.shiftKey) onPrevious();
            else onNext();
          } else if (e.key === "Escape") {
            e.preventDefault();
            onClose();
          }
        }}
        placeholder="Buscar no documento"
        aria-label="Buscar no documento"
        aria-invalid={noResults || undefined}
        className="h-8 min-w-0 flex-1 bg-transparent px-1 text-sm text-foreground outline-none placeholder:text-foreground-subtle [&::-webkit-search-cancel-button]:hidden"
      />
      <span
        aria-live="polite"
        className={cn(
          "shrink-0 px-1 font-mono text-xs whitespace-nowrap tabular-nums",
          noResults ? "text-danger" : "text-foreground-muted",
        )}
      >
        {noResults ? "Nenhum resultado" : hasQuery ? `${current + 1} de ${total}` : ""}
      </span>
      <IconButton
        aria-label="Ocorrência anterior"
        icon={<ChevronUp size={16} strokeWidth={1.75} aria-hidden />}
        onClick={onPrevious}
        disabled={total === 0}
        tooltipSide="bottom"
      />
      <IconButton
        aria-label="Próxima ocorrência"
        icon={<ChevronDown size={16} strokeWidth={1.75} aria-hidden />}
        onClick={onNext}
        disabled={total === 0}
        tooltipSide="bottom"
      />
      <IconButton
        aria-label="Fechar busca"
        icon={<X size={16} strokeWidth={1.75} aria-hidden />}
        onClick={onClose}
        tooltipSide="bottom"
      />
    </div>
  );
}
