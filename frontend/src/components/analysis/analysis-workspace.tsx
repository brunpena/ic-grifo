"use client";

import type { ReactNode } from "react";
import { Group, Panel, Separator, useDefaultLayout } from "react-resizable-panels";
import { cn } from "@/lib/utils";
import { safeLayoutStorage, usePersistentState } from "@/lib/use-persistent-state";
import type { AnalysisLayout } from "./panel-toggles";

export { type AnalysisLayout, PanelToggles } from "./panel-toggles";

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
          <Panel id="side" defaultSize="40" minSize={320} maxSize="70">
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
