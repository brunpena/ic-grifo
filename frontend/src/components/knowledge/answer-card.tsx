"use client";

import { ChevronDown } from "lucide-react";
import { type ReactNode, useId, useState } from "react";
import { CitationList, type CitedRule, StreamingCursor } from "@/components/chat/chat-message";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type AnswerCardProps = {
  question: string;
  children: ReactNode;
  streaming?: boolean;
  citations?: CitedRule[];
  onCitationHighlight?: (ruleId: string | null) => void;
  onCitationClick?: (ruleId: string) => void;
  defaultOpen?: boolean;
  className?: string;
};

/** Resposta da Base de regras, recolhível, com os chips das regras citadas. */
export function AnswerCard({
  question,
  children,
  streaming,
  citations = [],
  onCitationHighlight,
  onCitationClick,
  defaultOpen = true,
  className,
}: AnswerCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();

  return (
    <Card className={cn("flex flex-col p-0", className)} aria-busy={streaming || undefined}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-lg px-4 py-3 text-left transition-colors duration-150 ease-out hover:bg-surface-hover"
      >
        <span className="min-w-0 flex-1 truncate text-sm font-semibold">{question}</span>
        <ChevronDown
          size={16}
          strokeWidth={1.75}
          aria-hidden
          className={cn("shrink-0 text-foreground-subtle transition-transform duration-150 ease-out", open && "rotate-180")}
        />
        <span className="sr-only">{open ? "Recolher resposta" : "Expandir resposta"}</span>
      </button>
      <div id={contentId} hidden={!open} className="flex flex-col gap-3 border-t border-border px-4 py-3">
        <div className="text-sm leading-relaxed whitespace-pre-wrap text-foreground">
          {children}
          {streaming && <StreamingCursor />}
        </div>
        {citations.length > 0 && (
          <CitationList citations={citations} onHighlight={onCitationHighlight} onClick={onCitationClick} />
        )}
      </div>
    </Card>
  );
}
