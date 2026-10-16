"use client";

import { X } from "lucide-react";
import { type ReactNode, useEffect, useId, useRef } from "react";
import { cn } from "@/lib/utils";
import { IconButton } from "./icon-button";
import { OVERLAY_CLASSES } from "./popover";

type DialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  /** Botões de ação, alinhados à direita no rodapé. */
  footer?: ReactNode;
  className?: string;
};

/**
 * Janela modal sobre o <dialog> nativo: `showModal()` deixa o resto da página
 * inerte (o foco fica preso dentro dele), fecha com Esc e devolve o foco a quem
 * abriu.
 */
export function Dialog({ open, onOpenChange, title, description, children, footer, className }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onClose={() => onOpenChange(false)}
      // O próprio <dialog> só recebe o clique quando ele cai no fundo escurecido.
      onClick={(e) => {
        if (e.target === e.currentTarget) onOpenChange(false);
      }}
      className={cn(
        "m-auto w-[480px] max-w-[calc(100vw-32px)] p-0 open:animate-enter",
        "backdrop:bg-brand-navy/60",
        OVERLAY_CLASSES,
        className,
      )}
    >
      <div className="flex flex-col gap-4 p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h2 id={titleId} className="text-sm font-semibold">
              {title}
            </h2>
            {description && (
              <p id={descriptionId} className="text-[13px] text-foreground-muted">
                {description}
              </p>
            )}
          </div>
          <IconButton
            aria-label="Fechar"
            icon={<X size={16} strokeWidth={1.75} aria-hidden />}
            onClick={() => onOpenChange(false)}
            className="-mt-1 -mr-2"
          />
        </div>
        {children}
        {footer && <div className="flex justify-end gap-2">{footer}</div>}
      </div>
    </dialog>
  );
}
