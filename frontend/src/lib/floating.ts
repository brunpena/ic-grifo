"use client";

import { type RefObject, useLayoutEffect } from "react";

/** Qualquer coisa com posição na tela: um elemento ou um `Range` de seleção de texto. */
export type FloatingAnchor = { getBoundingClientRect(): DOMRect };

export type FloatingOptions = {
  placement?: "top" | "bottom" | "right";
  align?: "start" | "center" | "end";
  offset?: number;
};

const VIEWPORT_PADDING = 8;

/**
 * Posiciona um elemento `position: fixed` junto da âncora, virando para o outro
 * lado quando falta espaço e sem sair da tela. Escreve direto no estilo do
 * elemento para não causar uma renderização extra a cada rolagem.
 */
export function useFloatingPosition(
  open: boolean,
  anchorRef: RefObject<FloatingAnchor | null>,
  floatingRef: RefObject<HTMLElement | null>,
  { placement = "bottom", align = "center", offset = 6 }: FloatingOptions = {},
) {
  useLayoutEffect(() => {
    if (!open) return;

    const update = () => {
      const anchor = anchorRef.current;
      const el = floatingRef.current;
      if (!anchor || !el) return;

      const a = anchor.getBoundingClientRect();
      const w = el.offsetWidth;
      const h = el.offsetHeight;
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      if (placement === "right") {
        const top = Math.min(Math.max(a.top + a.height / 2 - h / 2, VIEWPORT_PADDING), vh - h - VIEWPORT_PADDING);
        el.style.top = `${Math.round(top)}px`;
        el.style.left = `${Math.round(a.right + offset)}px`;
        el.dataset.side = "right";
        return;
      }

      const fitsBelow = a.bottom + offset + h <= vh - VIEWPORT_PADDING;
      const fitsAbove = a.top - offset - h >= VIEWPORT_PADDING;
      let side = placement;
      if (side === "bottom" && !fitsBelow && fitsAbove) side = "top";
      else if (side === "top" && !fitsAbove && fitsBelow) side = "bottom";

      const top = side === "bottom" ? a.bottom + offset : a.top - offset - h;
      let left =
        align === "start" ? a.left : align === "end" ? a.right - w : a.left + a.width / 2 - w / 2;
      left = Math.min(Math.max(left, VIEWPORT_PADDING), vw - w - VIEWPORT_PADDING);

      el.style.top = `${Math.round(top)}px`;
      el.style.left = `${Math.round(left)}px`;
      el.dataset.side = side;
    };

    update();
    // O conteúdo pode mudar de tamanho com o elemento aberto (ex.: botão que vira formulário).
    const resize = new ResizeObserver(update);
    if (floatingRef.current) resize.observe(floatingRef.current);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      resize.disconnect();
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open, anchorRef, floatingRef, placement, align, offset]);
}
