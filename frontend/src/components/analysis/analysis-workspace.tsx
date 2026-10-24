"use client";

import { ListChecks, MessageSquare, Table2 } from "lucide-react";
import type { ReactNode } from "react";
import { Group, Panel, Separator, useDefaultLayout } from "react-resizable-panels";
import { cn } from "@/lib/utils";
import { safeLayoutStorage, usePersistentState } from "@/lib/use-persistent-state";

/** Painéis visíveis na tela de análise. Sem "rules" nem "table", o painel lateral fecha. */
export type AnalysisLayout = { chat: boolean; rules: boolean; table: boolean };

const DEFAULT_LAYOUT: AnalysisLayout = { chat: true, rules: true, table: false };

function parseLayout(value: unknown): AnalysisLayout | null {
  if (typeof value !== "object" || value === null) return null;
  const { chat, rules, table } = value as Record<string, unknown>;
  if (typeof chat !== "boolean" || typeof rules !== "boolean" || typeof table !== "boolean") return null;
  return { chat, rules, table };
}

/** Quais painéis estão abertos, lembrado entre recarregamentos (as larguras ficam no Group). */
export function useAnalysisLayout() {
  return usePersistentState("grifo:analysis-layout", DEFAULT_LAYOUT, parseLayout);
}

const TOGGLES: { key: keyof AnalysisLayout; label: string; icon: typeof ListChecks }[] = [
  { key: "chat", label: "Conversa", icon: MessageSquare },
  { key: "rules", label: "Regras", icon: ListChecks },
  { key: "table", label: "Tabela", icon: Table2 },
];

/** Botões de liga/desliga dos painéis (ficam sempre visíveis na barra do documento). */
export function PanelToggles({
  layout,
  onChange,
  counts,
}: {
  layout: AnalysisLayout;
  onChange: (layout: AnalysisLayout) => void;
  /** Número exibido ao lado do rótulo (ex.: regras). */
  counts?: Partial<Record<keyof AnalysisLayout, number>>;
}) {
  return (
    <div role="group" aria-label="Painéis" className="flex items-center gap-0.5 rounded-md bg-surface-muted p-0.5">
      {TOGGLES.map(({ key, label, icon: Icon }) => {
        const on = layout[key];
        const count = counts?.[key];
        return (
          <button
            key={key}
            type="button"
            aria-pressed={on}
            title={`${on ? "Esconder" : "Mostrar"} ${label.toLowerCase()}`}
            onClick={() => onChange({ ...layout, [key]: !on })}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded-sm px-2 text-xs font-medium text-foreground-muted transition-colors duration-150 ease-out hover:text-foreground",
              on && "bg-surface text-foreground shadow-sm",
            )}
          >
            <Icon size={14} strokeWidth={1.75} aria-hidden />
            <span className="hidden xl:inline">{label}</span>
            {count !== undefined && count > 0 && (
              <span className="font-mono text-[11px] text-foreground-subtle tabular-nums">{count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

type AnalysisWorkspaceProps = {
  layout: AnalysisLayout;
  chat: ReactNode;
  document: ReactNode;
  rules: ReactNode;
  table: ReactNode;
};

/**
 * Conversa | documento | painel lateral (regras e/ou tabela, um sobre o outro). Cada
 * combinação de painéis visíveis guarda suas próprias larguras no localStorage.
 */
export function AnalysisWorkspace({ layout, chat, document, rules, table }: AnalysisWorkspaceProps) {
  const side = layout.rules || layout.table;
  const panelIds = [...(layout.chat ? ["chat"] : []), "document", ...(side ? ["side"] : [])];
  const main = useDefaultLayout({ id: "grifo-analysis", panelIds, storage: safeLayoutStorage });
  const sideLayout = useDefaultLayout({ id: "grifo-analysis-side", storage: safeLayoutStorage });

  return (
    <Group id="grifo-analysis" orientation="horizontal" className="h-full" {...main}>
      {layout.chat && (
        <>
          <Panel id="chat" defaultSize="26" minSize={280} maxSize="45">
            {chat}
          </Panel>
          <ResizeHandle />
        </>
      )}
      <Panel id="document" minSize={360}>
        {document}
      </Panel>
      {side && (
        <>
          <ResizeHandle />
          <Panel id="side" defaultSize="36" minSize={320} maxSize="70">
            {layout.rules && layout.table ? (
              <Group id="grifo-analysis-side" orientation="vertical" className="h-full" {...sideLayout}>
                <Panel id="side-rules" defaultSize="50" minSize={160}>
                  {rules}
                </Panel>
                <ResizeHandle vertical />
                <Panel id="side-table" defaultSize="50" minSize={160}>
                  {table}
                </Panel>
              </Group>
            ) : layout.rules ? (
              rules
            ) : (
              table
            )}
          </Panel>
        </>
      )}
    </Group>
  );
}

/** Divisória de 1 px com área de clique de 8 px; fica em `accent` no hover e ao arrastar. */
export function ResizeHandle({ vertical = false }: { vertical?: boolean }) {
  return (
    <Separator
      className={cn(
        "relative bg-border outline-none transition-colors duration-150 ease-out after:absolute after:content-['']",
        vertical ? "h-px after:inset-x-0 after:-top-1 after:h-2" : "w-px after:inset-y-0 after:-left-1 after:w-2",
        "data-[separator=active]:bg-accent data-[separator=hover]:bg-accent focus-visible:bg-accent",
      )}
    />
  );
}
