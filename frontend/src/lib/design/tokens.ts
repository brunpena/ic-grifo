// Fonte única, no código, das cores da marca e dos grifos. Os grifos sobre o PDF
// são desenhados em JavaScript, então não podem depender só das variáveis CSS.
// As cores de RULE_TYPES precisam bater com as variáveis --rule-* do globals.css.

export type RuleType = "obrigacao" | "proibicao" | "prazo" | "condicao" | "outro";
export type RuleStatus = "pendente" | "validada" | "rejeitada";

export const BRAND = {
  cyan: "#22D3EE",
  blue500: "#0A84FF",
  blue600: "#0058F0",
  blue700: "#0038D6",
  navy: "#030A1F",
  gradient: "linear-gradient(135deg, #22D3EE 0%, #0A84FF 45%, #0038D6 100%)",
} as const;

export const RULE_TYPES: Record<RuleType, { label: string; color: string; cssVar: string }> = {
  obrigacao: { label: "Obrigação", color: "#10B981", cssVar: "var(--rule-obrigacao)" },
  proibicao: { label: "Proibição", color: "#F43F5E", cssVar: "var(--rule-proibicao)" },
  prazo: { label: "Prazo", color: "#F59E0B", cssVar: "var(--rule-prazo)" },
  condicao: { label: "Condição", color: "#A855F7", cssVar: "var(--rule-condicao)" },
  outro: { label: "Outro", color: "#64748B", cssVar: "var(--rule-outro)" },
};

export const RULE_STATUS: Record<
  RuleStatus,
  { label: string; icon: "circle-dashed" | "circle-check" | "circle-x" }
> = {
  pendente: { label: "Pendente", icon: "circle-dashed" },
  validada: { label: "Validada", icon: "circle-check" },
  rejeitada: { label: "Rejeitada", icon: "circle-x" },
};

export const HIGHLIGHT = {
  fillOpacity: 0.28,
  fillOpacityActive: 0.42,
  fillOpacityRejected: 0.1,
  activeOutlineWidth: 2,
  searchColor: "#0A84FF",
  searchCurrentColor: "#0038D6",
  searchFillOpacity: 0.3,
} as const;
