"use client";

import type { PageViewport, PDFDocumentProxy } from "pdfjs-dist";
import { useEffect, useState } from "react";
import type { PageRect } from "./highlight-layer";

export type SearchMatch = { page: number; rect: PageRect };

type PageItem = { str: string; folded: string; x: number; y: number; width: number; height: number };
type PageText = { viewport: PageViewport; items: PageItem[] };

const MIN_QUERY = 2;
const MAX_MATCHES = 2000;

/** Minúsculas e sem acento, caractere por caractere (os índices continuam valendo). */
function fold(text: string): string {
  let out = "";
  for (const char of text) {
    const base = char.normalize("NFD")[0] ?? char;
    const lower = base.toLowerCase();
    // Mantém o mesmo número de unidades UTF-16 do original.
    out += lower.length === char.length ? lower : char;
  }
  return out;
}

// O texto de cada documento é lido uma vez só, na primeira busca.
const textCache = new WeakMap<PDFDocumentProxy, Promise<PageText[]>>();

function loadText(doc: PDFDocumentProxy): Promise<PageText[]> {
  let cached = textCache.get(doc);
  if (!cached) {
    cached = (async () => {
      const pages: PageText[] = [];
      for (let n = 1; n <= doc.numPages; n++) {
        const page = await doc.getPage(n);
        const content = await page.getTextContent();
        const items: PageItem[] = [];
        for (const item of content.items) {
          if (!("str" in item) || !item.str) continue;
          const transform = item.transform.map(Number);
          items.push({
            str: item.str,
            folded: fold(item.str),
            x: transform[4],
            y: transform[5],
            width: item.width,
            height: item.height || Math.hypot(transform[2], transform[3]),
          });
        }
        pages.push({ viewport: page.getViewport({ scale: 1 }), items });
      }
      return pages;
    })();
    textCache.set(doc, cached);
  }
  return cached;
}

/** Retângulo (em frações da página) do pedaço [start, end) de um item de texto. */
function rectOf(item: PageItem, start: number, end: number, viewport: PageViewport): PageRect {
  const length = item.str.length || 1;
  const x0 = item.x + (item.width * start) / length;
  const x1 = item.x + (item.width * end) / length;
  // Do topo das letras até um pouco abaixo da linha de base (descendentes).
  const [ax, ay] = viewport.convertToViewportPoint(x0, item.y + item.height);
  const [bx, by] = viewport.convertToViewportPoint(x1, item.y - item.height * 0.2);
  return {
    x: Math.min(ax, bx) / viewport.width,
    y: Math.min(ay, by) / viewport.height,
    width: Math.abs(bx - ax) / viewport.width,
    height: Math.abs(by - ay) / viewport.height,
  };
}

function findMatches(pages: PageText[], query: string): SearchMatch[] {
  const needle = fold(query);
  const matches: SearchMatch[] = [];
  pages.forEach(({ viewport, items }, index) => {
    for (const item of items) {
      let at = item.folded.indexOf(needle);
      while (at >= 0) {
        matches.push({ page: index + 1, rect: rectOf(item, at, at + needle.length, viewport) });
        if (matches.length >= MAX_MATCHES) return;
        at = item.folded.indexOf(needle, at + needle.length);
      }
    }
  });
  return matches;
}

/**
 * Ocorrências do texto no PDF, ignorando maiúsculas e acentos. A busca vale dentro de cada
 * trecho de texto do pdf.js (em geral, uma linha); palavras quebradas entre linhas não entram.
 */
export function usePdfSearch(doc: PDFDocumentProxy | null, query: string) {
  const [result, setResult] = useState<{ doc: PDFDocumentProxy; query: string; matches: SearchMatch[] } | null>(null);
  const trimmed = query.trim();
  const active = !!doc && trimmed.length >= MIN_QUERY;

  useEffect(() => {
    if (!doc || trimmed.length < MIN_QUERY) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      loadText(doc)
        .then((pages) => {
          if (!cancelled) setResult({ doc, query: trimmed, matches: findMatches(pages, trimmed) });
        })
        .catch(() => {
          if (!cancelled) setResult({ doc, query: trimmed, matches: [] });
        });
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [doc, trimmed]);

  const current = active && result?.doc === doc && result.query === trimmed;
  return { matches: current ? result.matches : [], searching: active && !current };
}
