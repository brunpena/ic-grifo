"use client";

import { ChevronDown, History, LocateFixed } from "lucide-react";
import { useId, useState } from "react";
import { AssistantMessage, UserMessage } from "@/components/chat/chat-message";
import { RuleTypeBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { type Rule, useRules } from "@/lib/documents";
import { cn } from "@/lib/utils";

type ExcerptHistoryProps = {
  documentId: string;
  /** Leva ao trecho da regra no documento. */
  onGoToRule?: (ruleId: string) => void;
  /** Começa aberto (ex.: painel sem trecho em análise). */
  defaultOpen?: boolean;
  className?: string;
};

/**
 * Histórico do documento no painel da IA: as regras já aprovadas, com o trecho, a
 * interpretação e a conversa que levou a cada uma. A IA também recebe esse histórico.
 */
export function ExcerptHistory({ documentId, onGoToRule, defaultOpen = false, className }: ExcerptHistoryProps) {
  const rules = useRules(documentId, true);
  const [open, setOpen] = useState(defaultOpen);
  const listId = useId();
  const list = rules.data ?? [];

  return (
    <section aria-label="Histórico do documento" className={cn("rounded-lg border border-border", className)}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-[13px] font-medium"
      >
        <History size={14} strokeWidth={1.75} aria-hidden className="text-foreground-subtle" />
        <span className="flex-1">Regras já analisadas neste documento</span>
        {rules.isPending ? (
          <Spinner className="text-accent" />
        ) : (
          <span className="text-xs font-normal text-foreground-muted tabular-nums">{list.length}</span>
        )}
        <ChevronDown
          size={14}
          strokeWidth={1.75}
          aria-hidden
          className={cn("text-foreground-subtle transition-transform duration-150", open && "rotate-180")}
        />
      </button>
      {open && (
        <div id={listId} className="border-t border-border">
          {!rules.isPending && list.length === 0 ? (
            <p className="px-3 py-3 text-[13px] text-foreground-muted">
              Nenhuma regra aprovada ainda. As regras que você aprovar aparecem aqui, com a conversa.
            </p>
          ) : (
            <ul className="flex flex-col divide-y divide-border">
              {list.map((rule) => (
                <HistoryItem key={rule.id} rule={rule} onGoToRule={onGoToRule} />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function HistoryItem({ rule, onGoToRule }: { rule: Rule; onGoToRule?: (ruleId: string) => void }) {
  const [open, setOpen] = useState(false);
  const detailId = useId();
  return (
    <li>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={detailId}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full flex-col items-start gap-1 px-3 py-2.5 text-left hover:bg-surface-muted"
      >
        <span className="flex w-full items-center gap-2">
          <RuleTypeBadge type={rule.type} />
          <span className="text-[11px] text-foreground-subtle">
            {rule.page != null && `p. ${rule.page} · `}
            {rule.category === "csv" ? "Verificável no CSV" : "Regra geral"}
          </span>
          <ChevronDown
            size={14}
            strokeWidth={1.75}
            aria-hidden
            className={cn("ml-auto text-foreground-subtle transition-transform duration-150", open && "rotate-180")}
          />
        </span>
        <span className="text-[13px] text-foreground">{rule.summary}</span>
      </button>
      {open && (
        <div id={detailId} className="flex flex-col gap-3 px-3 pb-3">
          <blockquote className="max-h-32 overflow-y-auto rounded-md bg-surface-muted p-2.5 text-xs leading-relaxed text-foreground-muted">
            {rule.excerpt}
          </blockquote>
          {rule.interpretation && (
            <div className="flex flex-col gap-1">
              <span className="text-[11px] text-foreground-subtle">Interpretação</span>
              <p className="text-[13px] leading-relaxed whitespace-pre-wrap">{rule.interpretation}</p>
            </div>
          )}
          {rule.query?.sql_display && (
            <div className="flex flex-col gap-1">
              <span className="text-[11px] text-foreground-subtle">Busca aprovada</span>
              <pre className="max-h-32 overflow-auto rounded-md bg-surface-muted p-2.5 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
                {rule.query.sql_display}
              </pre>
            </div>
          )}
          <div className="flex flex-col gap-2">
            <span className="text-[11px] text-foreground-subtle">Conversa com a IA</span>
            {rule.conversation.length === 0 ? (
              <p className="text-[13px] text-foreground-muted">
                {rule.origin === "manual" ? "Regra criada à mão, sem conversa." : "Esta regra foi aprovada antes de a conversa ser guardada."}
              </p>
            ) : (
              <div role="log" aria-label={`Conversa da regra: ${rule.summary}`} className="flex flex-col gap-3">
                {rule.conversation.map((m, i) =>
                  m.role === "user" ? (
                    <UserMessage key={i}>{m.content}</UserMessage>
                  ) : (
                    <AssistantMessage key={i}>{m.content}</AssistantMessage>
                  ),
                )}
              </div>
            )}
          </div>
          {onGoToRule && rule.boxes.length > 0 && (
            <Button
              size="sm"
              variant="ghost"
              className="self-start"
              icon={<LocateFixed size={14} strokeWidth={1.75} aria-hidden />}
              onClick={() => onGoToRule(rule.id)}
            >
              Ver no documento
            </Button>
          )}
        </div>
      )}
    </li>
  );
}
