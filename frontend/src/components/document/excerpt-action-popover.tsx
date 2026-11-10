"use client";

import { Sparkles } from "lucide-react";
import type { RefObject } from "react";
import { Button } from "@/components/ui/button";
import { Popover } from "@/components/ui/popover";
import type { FloatingAnchor } from "@/lib/floating";

type ExcerptActionPopoverProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** A seleção de texto (`Range`) sobre a qual o botão aparece. */
  anchorRef: RefObject<FloatingAnchor | null>;
  onAnalyze: () => void;
  label?: string;
};

/** Botão logo acima do trecho selecionado: grifa e abre a conversa com a IA sobre ele. */
export function ExcerptActionPopover({
  open,
  onOpenChange,
  anchorRef,
  onAnalyze,
  label = "Grifar e analisar com IA",
}: ExcerptActionPopoverProps) {
  return (
    <Popover
      open={open}
      onOpenChange={onOpenChange}
      anchorRef={anchorRef}
      label="Analisar o trecho selecionado"
      placement="top"
      initialFocus={false}
      className="border-none bg-transparent p-0"
    >
      <Button
        size="sm"
        variant="primary"
        icon={<Sparkles size={16} strokeWidth={1.75} aria-hidden />}
        // Mantém a seleção de texto ao clicar.
        onMouseDown={(e) => e.preventDefault()}
        onClick={onAnalyze}
      >
        {label}
      </Button>
    </Popover>
  );
}
