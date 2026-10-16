"use client";

import { ArrowUp, Search } from "lucide-react";
import { IconButton } from "@/components/ui/icon-button";
import { cn } from "@/lib/utils";

type QuestionBarProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  loading?: boolean;
  placeholder?: string;
  className?: string;
};

/** Campo de pergunta largo, fixo no topo da Base de regras. */
export function QuestionBar({
  value,
  onChange,
  onSubmit,
  loading,
  placeholder = "Pergunte sobre as regras validadas",
  className,
}: QuestionBarProps) {
  const canSend = value.trim().length > 0 && !loading;
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSubmit();
      }}
      className={cn(
        "flex h-11 items-center gap-2 rounded-lg border border-border bg-surface pr-1.5 pl-3",
        "transition-[border-color,box-shadow] duration-150 ease-out focus-within:border-ring focus-within:ring-[3px] focus-within:ring-accent-soft",
        className,
      )}
    >
      <Search size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-foreground-subtle" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label="Pergunta sobre as regras"
        className="h-full min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-foreground-subtle"
      />
      <IconButton
        type="submit"
        variant="primary"
        aria-label="Enviar pergunta"
        icon={<ArrowUp size={16} strokeWidth={1.75} aria-hidden />}
        loading={loading}
        disabled={!canSend && !loading}
      />
    </form>
  );
}
