"use client";

import { ClipboardPaste, FileUp } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type UploadDropzoneProps = {
  onFile: (file: File) => void;
  onPasteText?: () => void;
  disabled?: boolean;
  className?: string;
};

/** Área de envio inicial: arrastar um PDF ou clicar para escolher. */
export function UploadDropzone({ onFile, onPasteText, disabled, className }: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  return (
    <div className={cn("flex flex-col items-center gap-3", className)}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files[0];
          if (file) onFile(file);
        }}
        className={cn(
          "flex w-full flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border-strong px-6 py-12",
          "text-center transition-colors duration-150 ease-out enabled:hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-50",
          dragging && "border-accent bg-accent-soft enabled:hover:bg-accent-soft",
        )}
      >
        <FileUp
          size={28}
          strokeWidth={1.5}
          aria-hidden
          className={cn("text-foreground-subtle", dragging && "text-accent")}
        />
        <span className="text-sm font-medium text-foreground">Arraste um PDF ou clique para enviar</span>
        <span className="text-xs text-foreground-subtle">Contratos, editais e regulamentos</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
      {onPasteText && (
        <Button
          variant="ghost"
          size="sm"
          icon={<ClipboardPaste size={16} strokeWidth={1.75} aria-hidden />}
          onClick={onPasteText}
          disabled={disabled}
        >
          Colar texto
        </Button>
      )}
    </div>
  );
}
