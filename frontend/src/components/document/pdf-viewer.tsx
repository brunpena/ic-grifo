import type { ReactNode, Ref, UIEventHandler } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type PdfViewerProps = {
  /** Barra de ferramentas e legenda, fixas no topo do painel. */
  header?: ReactNode;
  /** Elementos que flutuam sobre a área do documento (ex.: barra de busca). */
  overlay?: ReactNode;
  children: ReactNode;
  /** Área que rola (para acompanhar a página atual e navegar até uma regra). */
  scrollRef?: Ref<HTMLDivElement>;
  onScroll?: UIEventHandler<HTMLDivElement>;
  className?: string;
};

/** Painel do documento: o cabeçalho fica fixo e só as páginas rolam. */
export function PdfViewer({ header, overlay, children, scrollRef, onScroll, className }: PdfViewerProps) {
  return (
    <section aria-label="Documento" className={cn("relative flex h-full min-h-0 flex-col bg-viewer", className)}>
      {header}
      <div className="relative min-h-0 flex-1">
        <div ref={scrollRef} onScroll={onScroll} className="absolute inset-0 overflow-auto">
          <div className="flex min-w-fit flex-col items-center gap-4 p-4">{children}</div>
        </div>
        {overlay}
      </div>
    </section>
  );
}

type PdfPageProps = {
  /** Tamanho da página já com o zoom aplicado, em px. */
  width: number;
  height: number;
  pageNumber: number;
  loading?: boolean;
  /** Canvas ou camada de texto da página, e a camada de grifos por cima. */
  children?: ReactNode;
  className?: string;
};

/** Página do documento. Fica branca nos dois temas, como papel. */
export function PdfPage({ width, height, pageNumber, loading, children, className }: PdfPageProps) {
  return (
    <div
      role="region"
      aria-label={`Página ${pageNumber}`}
      aria-busy={loading || undefined}
      data-page={pageNumber}
      className={cn("paper relative shrink-0 bg-white shadow-sm", className)}
      style={{ width, height }}
    >
      {loading ? <Skeleton className="absolute inset-0 rounded-none bg-white" /> : children}
    </div>
  );
}
