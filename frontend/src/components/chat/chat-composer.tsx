"use client";

import { ArrowUp, Paperclip } from "lucide-react";
import { IconButton } from "@/components/ui/icon-button";
import { cn } from "@/lib/utils";

type ChatComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onAttach?: () => void;
  sending?: boolean;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
};

/** Campo de mensagem do rodapé da conversa. Enter envia, Shift+Enter quebra a linha. */
export function ChatComposer({
  value,
  onChange,
  onSubmit,
  onAttach,
  sending,
  disabled,
  placeholder = "Pergunte sobre o documento",
  className,
}: ChatComposerProps) {
  const canSend = value.trim().length > 0 && !sending && !disabled;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSubmit();
      }}
      className={cn(
        "flex items-end gap-1 rounded-lg border border-border bg-surface p-1.5",
        "transition-[border-color,box-shadow] duration-150 ease-out focus-within:border-ring focus-within:ring-[3px] focus-within:ring-accent-soft",
        className,
      )}
    >
      {onAttach && (
        <IconButton
          aria-label="Anexar arquivo"
          icon={<Paperclip size={16} strokeWidth={1.75} aria-hidden />}
          onClick={onAttach}
          disabled={disabled}
        />
      )}
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
        aria-label="Mensagem"
        disabled={disabled}
        className="field-sizing-content max-h-40 min-h-8 flex-1 resize-none bg-transparent px-1.5 py-1.5 text-sm text-foreground outline-none placeholder:text-foreground-subtle"
      />
      <IconButton
        type="submit"
        variant="primary"
        aria-label="Enviar mensagem"
        icon={<ArrowUp size={16} strokeWidth={1.75} aria-hidden />}
        loading={sending}
        disabled={!canSend && !sending}
      />
    </form>
  );
}
