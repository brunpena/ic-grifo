"use client";

import type { CSSProperties } from "react";
import { withAlpha } from "@/lib/design/color";
import { HIGHLIGHT, RULE_TYPES, type RuleStatus, type RuleType } from "@/lib/design/tokens";

/** Retângulo em frações da página (0 a 1), para independer do zoom. */
export type PageRect = { x: number; y: number; width: number; height: number };

/** Retângulos de uma seleção de texto dentro da página, em frações (recortados à página). */
export function selectionRects(range: Range, pageEl: HTMLElement): PageRect[] {
  const box = pageEl.getBoundingClientRect();
  if (!box.width || !box.height) return [];
  return Array.from(range.getClientRects()).flatMap((r) => {
    const left = Math.max(r.left, box.left);
    const top = Math.max(r.top, box.top);
    const right = Math.min(r.right, box.right);
    const bottom = Math.min(r.bottom, box.bottom);
    if (right - left < 1 || bottom - top < 1) return [];
    return [{
      x: (left - box.left) / box.width,
      y: (top - box.top) / box.height,
      width: (right - left) / box.width,
      height: (bottom - top) / box.height,
    }];
  });
}

export type RuleHighlight = {
  ruleId: string;
  type: RuleType;
  status: RuleStatus;
  rects: PageRect[];
};

type HighlightLayerProps = {
  highlights: RuleHighlight[];
  /** Regra selecionada ou em hover (na tabela, num chip ou no próprio grifo). */
  activeRuleId?: string | null;
  /**
   * Regra para onde se acabou de navegar. Mude `pulseKey` a cada navegação para
   * repetir o pulso, mesmo se for a mesma regra.
   */
  pulse?: { ruleId: string; key: number } | null;
  searchRects?: PageRect[];
  /** Trecho grifado em análise (ainda não é uma regra). */
  draftRects?: PageRect[];
  /** Índice, em `searchRects`, da ocorrência atual. */
  currentSearchIndex?: number;
  onHoverRule?: (ruleId: string | null) => void;
  onClickRule?: (ruleId: string) => void;
};

const toBox = (r: PageRect): CSSProperties => ({
  left: `${r.x * 100}%`,
  top: `${r.y * 100}%`,
  width: `${r.width * 100}%`,
  height: `${r.height * 100}%`,
});

function ruleStyle(h: RuleHighlight, active: boolean): CSSProperties {
  const color = RULE_TYPES[h.type].color;
  if (h.status === "rejeitada") {
    return {
      backgroundColor: withAlpha(color, HIGHLIGHT.fillOpacityRejected),
      outline: `1px dashed ${color}`,
      outlineWidth: active ? HIGHLIGHT.activeOutlineWidth : 1,
    };
  }
  return {
    backgroundColor: withAlpha(color, active ? HIGHLIGHT.fillOpacityActive : HIGHLIGHT.fillOpacity),
    outline: active ? `${HIGHLIGHT.activeOutlineWidth}px solid ${color}` : undefined,
  };
}

/**
 * Camada de grifos sobre uma página. Fica por cima do canvas, ocupando a página
 * inteira. É só visual: a navegação pelo teclado acontece pela tabela de regras.
 */
export function HighlightLayer({
  highlights,
  activeRuleId,
  pulse,
  searchRects = [],
  draftRects = [],
  currentSearchIndex,
  onHoverRule,
  onClickRule,
}: HighlightLayerProps) {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0">
      {highlights.map((h) => {
        const active = h.ruleId === activeRuleId;
        const pulsing = pulse?.ruleId === h.ruleId;
        const style = ruleStyle(h, active);
        return h.rects.map((rect, i) => (
          <div
            // A chave muda a cada navegação, remontando o elemento e repetindo o pulso.
            key={`${h.ruleId}-${i}-${pulsing ? pulse.key : ""}`}
            onPointerEnter={() => onHoverRule?.(h.ruleId)}
            onPointerLeave={() => onHoverRule?.(null)}
            onClick={() => onClickRule?.(h.ruleId)}
            className={
              "pointer-events-auto absolute cursor-pointer rounded-[2px] mix-blend-multiply transition-[background-color,outline-color] duration-150 ease-out" +
              (pulsing ? " animate-highlight-pulse" : "")
            }
            style={
              {
                ...toBox(rect),
                ...style,
                "--hl-pulse": withAlpha(RULE_TYPES[h.type].color, 0.6),
              } as CSSProperties
            }
          />
        ));
      })}

      {draftRects.map((rect, i) => (
        <div
          key={`draft-${i}`}
          className="absolute rounded-[2px] mix-blend-multiply"
          style={{
            ...toBox(rect),
            backgroundColor: withAlpha(HIGHLIGHT.draftColor, HIGHLIGHT.draftFillOpacity),
            outline: `1.5px dashed ${HIGHLIGHT.draftColor}`,
          }}
        />
      ))}

      {searchRects.map((rect, i) => (
        <div
          key={`search-${i}`}
          className="absolute rounded-[2px] mix-blend-multiply"
          style={{
            ...toBox(rect),
            backgroundColor: withAlpha(HIGHLIGHT.searchColor, HIGHLIGHT.searchFillOpacity),
            outline:
              i === currentSearchIndex
                ? `${HIGHLIGHT.activeOutlineWidth}px solid ${HIGHLIGHT.searchCurrentColor}`
                : undefined,
          }}
        />
      ))}
    </div>
  );
}
