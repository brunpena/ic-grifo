"use client";

import type { ReactNode } from "react";
import { BrandLogo } from "@/components/brand-logo";
import { RuleChip } from "@/components/rules/rule-chip";
import type { RuleType } from "@/lib/design/tokens";
import { cn } from "@/lib/utils";

export type CitedRule = { id: string; type: RuleType; summary: string };

export function UserMessage({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex justify-end", className)}>
      <div className="max-w-[85%] rounded-lg bg-accent-soft px-3 py-2 text-sm whitespace-pre-wrap text-foreground">
        <span className="sr-only">Você: </span>
        {children}
      </div>
    </div>
  );
}

/** Cursor discreto no fim do texto enquanto a resposta chega. */
export function StreamingCursor() {
  return (
    <span
      aria-hidden
      className="ml-0.5 inline-block h-[1.1em] w-0.5 translate-y-[0.2em] bg-accent animate-blink motion-reduce:animate-none"
    />
  );
}

type AssistantMessageProps = {
  children: ReactNode;
  streaming?: boolean;
  citations?: CitedRule[];
  onCitationHighlight?: (ruleId: string | null) => void;
  onCitationClick?: (ruleId: string) => void;
  className?: string;
};

/** Resposta da IA: sem balão, ocupando a largura da coluna. */
export function AssistantMessage({
  children,
  streaming,
  citations = [],
  onCitationHighlight,
  onCitationClick,
  className,
}: AssistantMessageProps) {
  return (
    <div className={cn("flex gap-3", className)} aria-busy={streaming || undefined}>
      <BrandLogo size={20} labelled={false} className="mt-0.5" />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="text-sm leading-relaxed whitespace-pre-wrap text-foreground">
          <span className="sr-only">Assistente: </span>
          {children}
          {streaming && <StreamingCursor />}
        </div>
        {citations.length > 0 && <CitationList citations={citations} onHighlight={onCitationHighlight} onClick={onCitationClick} />}
      </div>
    </div>
  );
}

export function CitationList({
  citations,
  onHighlight,
  onClick,
  className,
}: {
  citations: CitedRule[];
  onHighlight?: (ruleId: string | null) => void;
  onClick?: (ruleId: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <span className="text-xs text-foreground-subtle">Regras citadas</span>
      <ul className="flex flex-wrap gap-1.5">
        {citations.map((rule) => (
          <li key={rule.id} className="max-w-full">
            <RuleChip
              type={rule.type}
              summary={rule.summary}
              onHighlight={(on) => onHighlight?.(on ? rule.id : null)}
              onClick={() => onClick?.(rule.id)}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
