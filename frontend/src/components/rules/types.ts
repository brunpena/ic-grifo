import type { RuleStatus, RuleType } from "@/lib/design/tokens";

/** Resumo da busca da regra nas bases, para a tabela. */
export type RuleQuerySummary = {
  state: "pendente" | "ok" | "erro";
  match_count: number | null;
  error: string | null;
  dataset_name: string | null;
  /** A busca em português (ex.: "Valor maior que 50.000"). */
  description: string;
};

/** O que a interface precisa de uma regra para exibi-la (campos do modelo `Rule`). */
export type RuleView = {
  id: string;
  type: RuleType;
  status: RuleStatus;
  summary: string;
  excerpt: string;
  /** Página onde o trecho começa, quando conhecida. */
  page?: number;
  /** Busca nas bases; `undefined` quando a tela não trabalha com bases. */
  query?: RuleQuerySummary | null;
};
