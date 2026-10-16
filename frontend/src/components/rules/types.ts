import type { RuleStatus, RuleType } from "@/lib/design/tokens";

/** O que a interface precisa de uma regra para exibi-la (campos do modelo `Rule`). */
export type RuleView = {
  id: string;
  type: RuleType;
  status: RuleStatus;
  summary: string;
  excerpt: string;
  /** Página onde o trecho começa, quando conhecida. */
  page?: number;
};
