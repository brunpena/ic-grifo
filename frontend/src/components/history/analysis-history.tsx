"use client";

import { CircleCheck, CircleX, FileText, History, Loader2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { type DocumentInfo, useDocuments } from "@/lib/documents";
import { cn } from "@/lib/utils";

const DATE = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

const STATUS: Record<DocumentInfo["status"], { label: string; Icon: typeof CircleCheck; className: string }> = {
  ready: { label: "Pronto", Icon: CircleCheck, className: "bg-success-soft text-success" },
  processing: { label: "Lendo", Icon: Loader2, className: "bg-pending-soft text-pending" },
  extracting_rules: { label: "Analisando", Icon: Loader2, className: "bg-pending-soft text-pending" },
  error: { label: "Interrompido", Icon: CircleX, className: "bg-danger-soft text-danger" },
};

/** Documentos que a pessoa já analisou, do mais recente ao mais antigo. */
export function AnalysisHistory({
  currentDocumentId,
  onOpen,
  className,
}: {
  currentDocumentId?: string | null;
  onOpen: (document: DocumentInfo) => void;
  className?: string;
}) {
  const { data: documents, isPending, isError, error } = useDocuments();

  if (isPending) {
    return (
      <div role="status" aria-busy className={className}>
        <span className="sr-only">Carregando histórico</span>
        <ul aria-hidden className="flex flex-col gap-2">
        {[1, 2, 3, 4].map((n) => (
          <li key={n} aria-hidden className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2.5">
            <Skeleton className="size-[18px] shrink-0" />
            <span className="flex min-w-0 flex-1 flex-col gap-1.5">
              <Skeleton className={cn("h-3", n % 2 ? "w-3/4" : "w-1/2")} />
              <Skeleton className="h-2.5 w-28" />
            </span>
            <Skeleton className="h-6 w-20 shrink-0" />
          </li>
        ))}
        </ul>
      </div>
    );
  }
  if (isError) {
    return <p role="alert" className="text-sm text-danger">{errorMessage(error)}</p>;
  }
  if (!documents.length) {
    return (
      <p className={cn("flex items-center gap-2 text-sm text-foreground-muted", className)}>
        <History size={16} aria-hidden /> Nenhuma análise anterior.
      </p>
    );
  }

  return (
    <ul className={cn("flex flex-col gap-2", className)}>
      {documents.map((document) => {
        const status = STATUS[document.status];
        const current = document.id === currentDocumentId;
        return (
          <li key={document.id}>
            <button
              type="button"
              onClick={() => onOpen(document)}
              disabled={current}
              aria-current={current ? "true" : undefined}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2.5 text-left",
                "transition-colors duration-150 ease-out hover:bg-surface-muted disabled:cursor-default",
                current && "border-accent bg-accent-soft hover:bg-accent-soft",
              )}
            >
              <FileText size={18} strokeWidth={1.75} aria-hidden className="shrink-0 text-foreground-muted" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{document.title}</span>
                <span className="block text-xs text-foreground-muted">
                  {DATE.format(new Date(document.created_at))}
                  {document.page_count ? ` · ${document.page_count} pág.` : ""}
                  {current ? " · aberto agora" : ""}
                </span>
              </span>
              <span className={cn("inline-flex h-6 shrink-0 items-center gap-1.5 rounded-sm px-2 text-xs font-medium", status.className)}>
                <status.Icon size={14} strokeWidth={1.75} aria-hidden />
                {status.label}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
