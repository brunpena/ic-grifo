"use client";

import { ListChecks, MessageSquare, Table2 } from "lucide-react";
import { msg, useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

/** Painéis visíveis na tela de análise. Sem "rules" nem "table", o painel lateral fecha. */
export type AnalysisLayout = { chat: boolean; rules: boolean; table: boolean };

const TOGGLES: { key: keyof AnalysisLayout; label: string; icon: typeof ListChecks }[] = [
  { key: "chat", label: msg("Conversa"), icon: MessageSquare },
  { key: "rules", label: msg("Regras"), icon: ListChecks },
  { key: "table", label: msg("Tabela"), icon: Table2 },
];

/**
 * Botões de liga/desliga dos painéis (ficam sempre visíveis na barra do documento).
 * Fica fora de `analysis-workspace.tsx` para não puxar o `react-resizable-panels` junto.
 */
export function PanelToggles({
  layout,
  onChange,
  counts,
  hiddenPanels = [],
}: {
  layout: AnalysisLayout;
  onChange: (layout: AnalysisLayout) => void;
  /** Número exibido ao lado do rótulo (ex.: regras). */
  counts?: Partial<Record<keyof AnalysisLayout, number>>;
  hiddenPanels?: (keyof AnalysisLayout)[];
}) {
  const t = useT();
  return (
    <div role="group" aria-label={t("Painéis")} className="flex items-center gap-0.5 rounded-md bg-surface-muted p-0.5">
      {TOGGLES.filter(({ key }) => !hiddenPanels.includes(key)).map(({ key, label, icon: Icon }) => {
        const on = layout[key];
        const count = counts?.[key];
        const text = t(label);
        return (
          <button
            key={key}
            type="button"
            aria-pressed={on}
            title={on ? t("Esconder {panel}", { panel: text.toLowerCase() }) : t("Mostrar {panel}", { panel: text.toLowerCase() })}
            onClick={() => onChange({ ...layout, [key]: !on })}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded-sm px-2 text-xs font-medium text-foreground-muted transition-colors duration-150 ease-out hover:text-foreground",
              on && "bg-surface text-foreground shadow-sm",
            )}
          >
            <Icon size={14} strokeWidth={1.75} aria-hidden />
            <span className="hidden xl:inline">{text}</span>
            {count !== undefined && count > 0 && (
              <span className="font-mono text-[11px] text-foreground-subtle tabular-nums">{count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
