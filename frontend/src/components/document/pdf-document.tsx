"use client";

import type { PDFDocumentProxy, RenderTask, TextLayer } from "pdfjs-dist";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { PdfPage } from "./pdf-viewer";

/** 100% de zoom = tamanho real da página na tela (pontos PDF → pixels CSS). */
export const PDF_TO_CSS = 96 / 72;

export type PdfPageSize = { width: number; height: number };

type LoadState =
  | { status: "idle" }
  | { status: "loading"; file: File }
  | { status: "ready"; file: File; doc: PDFDocumentProxy; pages: PdfPageSize[] }
  | { status: "error"; file: File; message: string };

async function loadPdfJs() {
  const pdfjs = await import("pdfjs-dist");
  if (!pdfjs.GlobalWorkerOptions.workerSrc) {
    pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
  }
  return pdfjs;
}

/** Abre um PDF local com o pdf.js e lê o tamanho de cada página. */
export function usePdfDocument(file: File | null): LoadState {
  const [state, setState] = useState<LoadState>({ status: "idle" });

  useEffect(() => {
    if (!file) return;
    let cancelled = false;
    let destroy: (() => void) | undefined;

    (async () => {
      const pdfjs = await loadPdfJs();
      const task = pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) });
      destroy = () => void task.destroy();
      const doc = await task.promise;
      const pages = await Promise.all(
        Array.from({ length: doc.numPages }, async (_, i) => {
          const viewport = (await doc.getPage(i + 1)).getViewport({ scale: 1 });
          return { width: viewport.width, height: viewport.height };
        }),
      );
      if (!cancelled) setState({ status: "ready", file, doc, pages });
    })().catch((error: unknown) => {
      if (cancelled) return;
      const message =
        error instanceof Error && error.name === "PasswordException"
          ? "Este PDF é protegido por senha."
          : "Não foi possível abrir este PDF. Confira se o arquivo não está corrompido.";
      setState({ status: "error", file, message });
    });

    return () => {
      cancelled = true;
      destroy?.();
    };
  }, [file]);

  if (!file) return { status: "idle" };
  // Enquanto o arquivo novo carrega, o estado ainda é do anterior.
  return "file" in state && state.file === file ? state : { status: "loading", file };
}

type PdfDocumentPagesProps = {
  doc: PDFDocumentProxy;
  pages: PdfPageSize[];
  zoom: number;
  /** Camadas sobre cada página (grifos). Ficam entre o canvas e a camada de texto. */
  renderOverlay?: (pageNumber: number) => ReactNode;
  onPageMouseUp?: (pageNumber: number, pageElement: HTMLElement) => void;
  /** Clique sem seleção de texto, com a posição em frações da página. */
  onPageClick?: (pageNumber: number, point: { x: number; y: number }) => void;
};

export function PdfDocumentPages({ doc, pages, zoom, renderOverlay, onPageMouseUp, onPageClick }: PdfDocumentPagesProps) {
  return pages.map((size, i) => (
    <PdfPageView
      key={i}
      doc={doc}
      pageNumber={i + 1}
      size={size}
      zoom={zoom}
      overlay={renderOverlay?.(i + 1)}
      onMouseUp={onPageMouseUp}
      onClick={onPageClick}
    />
  ));
}

function PdfPageView({
  doc,
  pageNumber,
  size,
  zoom,
  overlay,
  onMouseUp,
  onClick,
}: {
  doc: PDFDocumentProxy;
  pageNumber: number;
  size: PdfPageSize;
  zoom: number;
  overlay?: ReactNode;
  onMouseUp?: PdfDocumentPagesProps["onPageMouseUp"];
  onClick?: PdfDocumentPagesProps["onPageClick"];
}) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [rendered, setRendered] = useState(false);
  const width = size.width * zoom * PDF_TO_CSS;
  const height = size.height * zoom * PDF_TO_CSS;

  // Só desenha a página quando ela chega perto da área visível.
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "800px 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    let renderTask: RenderTask | undefined;
    let textLayer: TextLayer | undefined;

    (async () => {
      const pdfjs = await loadPdfJs();
      const page = await doc.getPage(pageNumber);
      const canvas = canvasRef.current;
      const container = textRef.current;
      if (cancelled || !canvas || !container) return;

      const viewport = page.getViewport({ scale: zoom * PDF_TO_CSS });
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      renderTask = page.render({
        canvas,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
      });
      await renderTask.promise;
      if (cancelled) return;

      container.replaceChildren();
      container.style.setProperty("--total-scale-factor", String(viewport.scale));
      textLayer = new pdfjs.TextLayer({ textContentSource: page.streamTextContent(), container, viewport });
      await textLayer.render();
      if (!cancelled) setRendered(true);
    })().catch((error: unknown) => {
      if (error instanceof Error && error.name === "RenderingCancelledException") return;
      console.error(error);
    });

    return () => {
      cancelled = true;
      renderTask?.cancel();
      textLayer?.cancel();
    };
  }, [visible, doc, pageNumber, zoom]);

  return (
    <div
      ref={wrapperRef}
      onMouseUp={(e) => onMouseUp?.(pageNumber, e.currentTarget.firstElementChild as HTMLElement)}
      onClick={(e) => {
        if (!onClick || !window.getSelection()?.isCollapsed) return;
        const box = (e.currentTarget.firstElementChild as HTMLElement).getBoundingClientRect();
        onClick(pageNumber, { x: (e.clientX - box.left) / box.width, y: (e.clientY - box.top) / box.height });
      }}
    >
      <PdfPage width={width} height={height} pageNumber={pageNumber}>
        <canvas ref={canvasRef} aria-hidden className="absolute inset-0 size-full" />
        {overlay}
        <div ref={textRef} className="textLayer" />
        {!rendered && <Skeleton className="absolute inset-0 rounded-none bg-white" />}
      </PdfPage>
    </div>
  );
}
