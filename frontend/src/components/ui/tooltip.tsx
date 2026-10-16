"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { type FloatingAnchor, useFloatingPosition } from "@/lib/floating";
import { cn } from "@/lib/utils";

type TooltipProps = {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom" | "right";
  /** Atraso para abrir no hover do mouse, em ms. No foco pelo teclado abre na hora. */
  delay?: number;
  className?: string;
};

/**
 * Dica visual. Fica oculta para leitores de tela: o mesmo texto deve estar no
 * próprio elemento (aria-label do IconButton, texto completo da célula truncada).
 */
export function Tooltip({ content, children, side = "top", delay = 400, className }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const timer = useRef<number | undefined>(undefined);
  // Sem `className`, o invólucro usa `display: contents` (não tem caixa própria),
  // então o tooltip se posiciona pelo elemento de dentro.
  const anchorRef = useRef<FloatingAnchor>({
    getBoundingClientRect: () => {
      const wrapper = triggerRef.current!;
      return (wrapper.firstElementChild ?? wrapper).getBoundingClientRect();
    },
  });

  useFloatingPosition(open, anchorRef, tipRef, { placement: side });

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const hide = () => {
    window.clearTimeout(timer.current);
    setOpen(false);
  };

  return (
    <span
      ref={triggerRef}
      className={className ?? "contents"}
      onPointerEnter={(e) => {
        if (e.pointerType !== "mouse") return;
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => setOpen(true), delay);
      }}
      onPointerLeave={hide}
      onFocus={(e) => {
        if (e.target.matches(":focus-visible")) setOpen(true);
      }}
      onBlur={hide}
    >
      {children}
      {open &&
        createPortal(
          <div
            ref={tipRef}
            aria-hidden
            className={cn(
              "pointer-events-none fixed top-0 left-0 z-50 max-w-80 rounded-lg border border-border bg-surface",
              "px-2 py-1 text-xs text-foreground shadow-md animate-enter",
            )}
          >
            {content}
          </div>,
          document.body,
        )}
    </span>
  );
}
