"use client";

import { Download, Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type PdfToolbarProps = {
  /** 1 = 100%. */
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomReset?: () => void;
  minZoom?: number;
  maxZoom?: number;
  page: number;
  pageCount: number;
  onExport?: () => void;
  exporting?: boolean;
  /** Botões extras à direita (busca, painéis). */
  actions?: ReactNode;
  className?: string;
};

export function PdfToolbar({
  zoom,
  onZoomIn,
  onZoomOut,
  onZoomReset,
  minZoom = 0.5,
  maxZoom = 3,
  page,
  pageCount,
  onExport,
  exporting,
  actions,
  className,
}: PdfToolbarProps) {
  const percent = `${Math.round(zoom * 100)}%`;
  return (
    <div
      role="toolbar"
      aria-label="Ferramentas do documento"
      className={cn("flex h-11 shrink-0 items-center gap-2 border-b border-border bg-surface px-2", className)}
    >
      <div className="flex items-center">
        <IconButton
          aria-label="Diminuir zoom"
          icon={<Minus size={16} strokeWidth={1.75} aria-hidden />}
          onClick={onZoomOut}
          disabled={zoom <= minZoom}
          tooltipSide="bottom"
        />
        <button
          type="button"
          onClick={onZoomReset}
          disabled={!onZoomReset}
          aria-label={`Zoom em ${percent}${onZoomReset ? ". Voltar para 100%" : ""}`}
          className="h-8 w-14 rounded-md font-mono text-xs text-foreground-muted tabular-nums transition-colors duration-150 ease-out enabled:hover:bg-surface-hover"
        >
          {percent}
        </button>
        <IconButton
          aria-label="Aumentar zoom"
          icon={<Plus size={16} strokeWidth={1.75} aria-hidden />}
          onClick={onZoomIn}
          disabled={zoom >= maxZoom}
          tooltipSide="bottom"
        />
      </div>

      <span className="mx-auto font-mono text-xs text-foreground-muted tabular-nums" aria-live="polite">
        <span className="sr-only">Página </span>
        {page} / {pageCount}
      </span>

      {onExport && (
        <Button
          size="sm"
          variant="primary"
          icon={<Download size={16} strokeWidth={1.75} aria-hidden />}
          loading={exporting}
          onClick={onExport}
        >
          Exportar
        </Button>
      )}
      {actions && <div className="flex items-center gap-1">{actions}</div>}
    </div>
  );
}
