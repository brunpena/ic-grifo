"use client";

import { ArrowUp, ChevronDown, FileText, Plus } from "lucide-react";
import { IconButton } from "@/components/ui/icon-button";
import { cn } from "@/lib/utils";

type AssistantComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  /** Abre o seletor de arquivo (PDF). */
  onAttach: () => void;
  documentName?: string | null;
  /** Mostra a pílula com o documento atual. */
  showDocument?: boolean;
  placeholder?: string;
  className?: string;
};

/**
 * Campo de mensagem em formato de pílula, no estilo do chat do lineFlow: anexar à
 * esquerda, documento atual e enviar à direita. Enter envia, Shift+Enter quebra a linha.
 */
export function AssistantComposer({
  value,
  onChange,
  onSubmit,
  onAttach,
  documentName,
  showDocument = true,
  placeholder = "Pergunte ao Grifo ou envie um documento…",
  className,
}: AssistantComposerProps) {
  const canSend = value.trim().length > 0;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSubmit();
      }}
      className={cn(
        "flex items-end gap-1.5 rounded-[24px] border border-border bg-surface/80 p-1.5 shadow-sm backdrop-blur",
        "transition-[border-color,box-shadow] duration-150 ease-out focus-within:border-ring focus-within:ring-[3px] focus-within:ring-accent-soft",
        "dark:bg-surface/60",
        className,
      )}
    >
      <IconButton
        aria-label="Enviar documento PDF"
        icon={<Plus size={18} strokeWidth={1.75} aria-hidden />}
        onClick={onAttach}
        className="size-9 rounded-full"
      />
      <textarea
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (canSend) onSubmit();
          }
        }}
        placeholder={placeholder}
        aria-label="Mensagem para o assistente"
        className="field-sizing-content max-h-40 min-h-9 min-w-0 flex-1 resize-none bg-transparent px-1 py-2 text-sm text-foreground outline-none placeholder:text-foreground-subtle"
      />
      {showDocument && (
        <button
          type="button"
          onClick={onAttach}
          className={cn(
            "mb-0.5 hidden h-8 max-w-48 shrink-0 items-center gap-1.5 rounded-full border border-border bg-accent-soft/50 px-3 text-xs font-medium text-foreground-muted sm:inline-flex",
            "transition-colors duration-150 ease-out hover:border-border-strong hover:text-foreground",
          )}
        >
          <FileText size={14} strokeWidth={1.75} aria-hidden className="shrink-0 text-accent" />
          <span className="truncate">{documentName ?? "Nenhum documento"}</span>
          <ChevronDown size={14} strokeWidth={1.75} aria-hidden className="shrink-0" />
          <span className="sr-only">. Trocar documento</span>
        </button>
      )}
      <IconButton
        type="submit"
        variant={canSend ? "primary" : "secondary"}
        aria-label="Enviar mensagem"
        icon={<ArrowUp size={16} strokeWidth={2} aria-hidden />}
        disabled={!canSend}
        className="size-9 rounded-full"
      />
    </form>
  );
}

export function AssistantDisclaimer({ className }: { className?: string }) {
  return (
    <p className={cn("text-center text-[11px] text-foreground-subtle", className)}>
      O Grifo usa IA para encontrar regras e pode errar. Confira sempre o trecho original antes de validar.
    </p>
  );
}
