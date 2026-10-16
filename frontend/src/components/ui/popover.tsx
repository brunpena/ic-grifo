"use client";

import { type ReactNode, type RefObject, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { type FloatingAnchor, type FloatingOptions, useFloatingPosition } from "@/lib/floating";
import { cn } from "@/lib/utils";

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export const OVERLAY_CLASSES =
  "rounded-lg border border-border bg-surface text-foreground shadow-md animate-enter";

type PopoverProps = FloatingOptions & {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Elemento que abriu o popover, ou um `Range` (ex.: a seleção de texto no PDF). */
  anchorRef: RefObject<FloatingAnchor | null>;
  /** Nome acessível do popover. */
  label: string;
  /** Move o foco para dentro ao abrir. Desligue para não desfazer uma seleção de texto. */
  initialFocus?: boolean;
  className?: string;
  children: ReactNode;
};

/** Painel flutuante não modal. Fecha com Esc e com clique fora. */
export function Popover({
  open,
  onOpenChange,
  anchorRef,
  label,
  initialFocus = true,
  className,
  children,
  placement,
  align,
  offset,
}: PopoverProps) {
  const ref = useRef<HTMLDivElement>(null);
  useFloatingPosition(open, anchorRef, ref, { placement, align, offset });

  useEffect(() => {
    if (!open || !initialFocus) return;
    const el = ref.current;
    const first = el?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? el)?.focus();
  }, [open, initialFocus]);

  useEffect(() => {
    if (!open) return;
    const el = ref.current;
    if (!el) return;

    const anchorNode = () => (anchorRef.current instanceof Node ? anchorRef.current : null);
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (!el.contains(target) && !anchorNode()?.contains(target)) onOpenChange(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      onOpenChange(false);
      const anchor = anchorNode();
      if (anchor instanceof HTMLElement) anchor.focus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, anchorRef, onOpenChange]);

  if (!open) return null;
  return createPortal(
    <div
      ref={ref}
      role="dialog"
      aria-label={label}
      tabIndex={-1}
      className={cn("fixed top-0 left-0 z-40 p-3 outline-none", OVERLAY_CLASSES, className)}
    >
      {children}
    </div>,
    document.body,
  );
}
