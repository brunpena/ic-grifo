"use client";

import type { CSSProperties } from "react";
import { withAlpha } from "@/lib/design/color";
import { HIGHLIGHT, RULE_TYPES, type RuleStatus, type RuleType } from "@/lib/design/tokens";

/** Retângulo em frações da página (0 a 1), para independer do zoom. */
export type PageRect = { x: number; y: number; width: number; height: number };

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
