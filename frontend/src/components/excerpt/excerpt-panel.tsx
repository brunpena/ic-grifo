"use client";

import { AlertTriangle, Check, Database, FileText, MousePointerClick, Play, RotateCcw, X } from "lucide-react";
import { type Ref, useEffect, useId, useImperativeHandle, useRef, useState } from "react";
import { AssistantMessage, UserMessage } from "@/components/chat/chat-message";
import { ChatComposer } from "@/components/chat/chat-composer";
import { QueryBuilder, useQueryBuilder } from "@/components/queries/query-builder";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, FormError } from "@/components/ui/field";
import { IconButton } from "@/components/ui/icon-button";
import { Input, Textarea } from "@/components/ui/input";
import { RuleTypeSelect } from "@/components/ui/rule-type-select";
import { Spinner } from "@/components/ui/spinner";
import type { Dataset } from "@/lib/analyses";
import { errorMessage } from "@/lib/api";
import {
  type ExcerptMessage,
  type Rule,
  type RuleCategory,
  type RuleProposal,
  type RuleType,
  useAnalyzeExcerpt,
  useCreateRule,
  usePreviewQuery,
} from "@/lib/documents";
import type { StructuredQuery } from "@/lib/queries";
import { cn } from "@/lib/utils";

/** Um trecho grifado no documento, aberto para análise. `key` muda a cada novo grifo. */
export type ExcerptSelection = { key: number; page: number; text: string };

type ExcerptPanelProps = {
  selection: ExcerptSelection;
  documentId: string;
  /** Bases prontas da análise: a busca só pode usar estas. */
  datasets: Dataset[];
  /** Esconde o painel; a conversa continua para quando ele abrir de novo. */
  onHide: () => void;
  /** Encerra a conversa sem salvar nada. */
  onDiscard: () => void;
  onApproved: (rule: Rule) => void;
  className?: string;
};

const OPENING = "Analise o trecho grifado.";

/**
 * Subtela de conversa com a IA sobre um trecho grifado. A IA classifica o trecho e
 * propõe a regra; a pessoa revisa, ajusta (à mão ou pedindo à IA) e só então aprova.
 * Nada é salvo antes da aprovação.
 */
export function ExcerptPanel({ selection, documentId, datasets, onHide, onDiscard, onApproved, className }: ExcerptPanelProps) {
  const analyze = useAnalyzeExcerpt(documentId);
  const create = useCreateRule(documentId);
  const [messages, setMessages] = useState<ExcerptMessage[]>([]);
  // A cada resposta da IA a revisão recomeça da nova proposta (versão nova = formulário novo).
  const [proposal, setProposal] = useState<{ value: RuleProposal; version: number } | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const review = useRef<ReviewHandle | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  const ask = (history: ExcerptMessage[]) => {
    setFailure(null);
    analyze.mutate(
      {
        page: selection.page,
        excerpt: selection.text,
        messages: history,
        current: review.current?.current() ?? null,
      },
      {
        onSuccess: (result) => {
          setMessages([...history, { role: "assistant", content: result.reply }]);
          setProposal((p) => ({ value: result.proposal, version: (p?.version ?? 0) + 1 }));
        },
        onError: (error) => setFailure(errorMessage(error)),
      },
    );
  };

  // Ao abrir, a IA analisa o trecho sem esperar uma pergunta.
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    ask([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [messages.length, analyze.isPending]);

  const send = () => {
    const content = draft.trim();
    if (!content || analyze.isPending) return;
    setDraft("");
    const base = messages.length ? messages : [{ role: "user" as const, content: OPENING }];
    const history = [...base, { role: "user" as const, content }];
    setMessages(history);
    ask(history);
  };

  // A primeira mensagem (pedido automático de análise) não aparece na conversa.
  const visible = messages.filter((m, i) => !(i === 0 && m.role === "user" && m.content === OPENING));

  return (
    <aside
      aria-labelledby={titleId}
      className={cn("flex h-full min-h-0 flex-col bg-surface", className)}
    >
      <header className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-3">
        <div className="min-w-0 flex-1">
          <h2 id={titleId} className="text-sm font-medium">Análise do trecho grifado</h2>
          <p className="text-xs text-foreground-muted">Página {selection.page} · nada é salvo sem a sua aprovação</p>
        </div>
        <IconButton aria-label="Esconder painel da IA" icon={<X size={16} strokeWidth={1.75} aria-hidden />} onClick={onHide} />
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4">
        <blockquote className="flex gap-2 rounded-md bg-surface-muted p-3 text-[13px] leading-relaxed text-foreground">
          <FileText size={16} strokeWidth={1.75} aria-hidden className="mt-0.5 shrink-0 text-foreground-subtle" />
          <span className="max-h-40 overflow-y-auto">{selection.text}</span>
        </blockquote>

        <div role="log" aria-live="polite" aria-label="Conversa com a IA" className="flex flex-col gap-3">
          {visible.map((m, i) =>
            m.role === "user" ? (
              <UserMessage key={i}>{m.content}</UserMessage>
            ) : (
              <AssistantMessage key={i}>{m.content}</AssistantMessage>
            ),
          )}
          {analyze.isPending && (
            <p className="flex items-center gap-2 text-[13px] text-foreground-muted">
              <Spinner className="text-accent" />
              {proposal ? "Ajustando a proposta…" : "Analisando o trecho…"}
            </p>
          )}
          {failure && (
            <div role="alert" className="flex flex-col items-start gap-2 rounded-md bg-danger-soft p-3 text-[13px]">
              <p>{failure}</p>
              <Button
                size="sm"
                icon={<RotateCcw size={16} strokeWidth={1.75} aria-hidden />}
                onClick={() => ask(messages.length && messages.at(-1)?.role === "user" ? messages : [])}
              >
                Tentar de novo
              </Button>
            </div>
          )}
        </div>

        {proposal && (
          <ProposalReview
            key={proposal.version}
            proposal={proposal.value}
            datasets={datasets}
            documentId={documentId}
            handleRef={review}
            busy={analyze.isPending}
          />
        )}
        <div ref={endRef} />
      </div>

      <div className="flex shrink-0 flex-col gap-3 border-t border-border p-3">
        <ChatComposer
          value={draft}
          onChange={setDraft}
          onSubmit={send}
          sending={analyze.isPending}
          disabled={!proposal && !failure}
          placeholder="Pergunte ou peça um ajuste à IA"
        />
        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onDiscard}>
            Descartar
          </Button>
          <Button
            variant="primary"
            icon={<Check size={16} strokeWidth={1.75} aria-hidden />}
            disabled={!proposal || analyze.isPending}
            loading={create.isPending}
            onClick={() => {
              const body = review.current?.approve();
              if (!body) return;
              create.mutate(
                { ...body, page: selection.page, excerpt: selection.text, origin: "ia" },
                {
                  onSuccess: onApproved,
                  onError: (error) => review.current?.fail(errorMessage(error)),
                },
              );
            }}
          >
            Aprovar regra
          </Button>
        </div>
      </div>
    </aside>
  );
}

/** Painel da IA aberto sem trecho grifado: explica como começar. */
export function ExcerptPanelEmpty({ onHide, className }: { onHide: () => void; className?: string }) {
  return (
    <aside aria-label="IA" className={cn("flex h-full min-h-0 flex-col bg-surface", className)}>
      <header className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-3">
        <h2 className="min-w-0 flex-1 text-sm font-medium">Análise com IA</h2>
        <IconButton aria-label="Esconder painel da IA" icon={<X size={16} strokeWidth={1.75} aria-hidden />} onClick={onHide} />
      </header>
      <EmptyState
        icon={MousePointerClick}
        title="Nenhum trecho em análise"
        description="Selecione um trecho do documento e clique em “Grifar e analisar com IA”. A conversa aparece aqui."
        className="flex-1"
      />
    </aside>
  );
}

type ReviewedRule = {
  category: RuleCategory;
  type: RuleType;
  summary: string;
  interpretation: string;
  query: StructuredQuery | null;
};

type ReviewHandle = {
  /** A proposta como está na tela, para a IA ajustar a partir dela. */
  current: () => ReviewedRule;
  /** Valida a revisão e devolve o que será salvo, ou `null` mostrando o problema. */
  approve: () => ReviewedRule | null;
  fail: (message: string) => void;
};

const EMPTY_QUERY = (datasets: Dataset[]): StructuredQuery => ({ dataset: datasets[0]?.name ?? "", logic: "and", conditions: [] });

function ProposalReview({
  proposal,
  datasets,
  documentId,
  handleRef,
  busy,
}: {
  proposal: RuleProposal;
  datasets: Dataset[];
  documentId: string;
  handleRef: Ref<ReviewHandle>;
  busy: boolean;
}) {
  const ids = useId();
  const [category, setCategory] = useState<RuleCategory>(proposal.category);
  const [type, setType] = useState<RuleType>(proposal.type);
  const [summary, setSummary] = useState(proposal.summary);
  const [interpretation, setInterpretation] = useState(proposal.interpretation);
  const [error, setError] = useState<string | null>(null);
  const builder = useQueryBuilder(proposal.query ?? EMPTY_QUERY(datasets), datasets);
  const preview = usePreviewQuery(documentId);
  // Resultado mostrado: o da IA até a primeira edição; depois, o do último teste.
  const [result, setResult] = useState<{ sql: string | null; count: number | null; error: string | null } | null>(
    proposal.query ? { sql: proposal.sql_display, count: proposal.match_count, error: proposal.query_error } : null,
  );

  const fields = (): ReviewedRule => ({
    category,
    type,
    summary: summary.trim(),
    interpretation: interpretation.trim(),
    query: category === "csv" ? builder.build() : null,
  });

  useImperativeHandle(handleRef, () => ({
    current: () => fields(),
    approve: () => {
      setError(null);
      const value = fields();
      if (!value.summary) {
        setError("Escreva um resumo da regra.");
        return null;
      }
      if (value.category === "csv" && !value.query) return null;
      return value;
    },
    fail: setError,
  }));

  const test = () => {
    const query = builder.build();
    if (!query) return;
    preview.mutate(query, {
      onSuccess: (r) => setResult({ sql: r.sql_display, count: r.match_count, error: null }),
      onError: (e) => setResult({ sql: null, count: null, error: errorMessage(e) }),
    });
  };

  return (
    <section
      aria-label="Proposta da IA para revisão"
      aria-busy={busy || undefined}
      className={cn("flex flex-col gap-4 rounded-lg border border-border p-4 transition-opacity", busy && "opacity-60")}
    >
      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">Revise antes de aprovar</h3>
        {!proposal.is_rule && (
          <p className="flex items-start gap-2 rounded-md bg-pending-soft px-2.5 py-2 text-xs text-foreground-muted">
            <AlertTriangle size={14} strokeWidth={1.75} aria-hidden className="mt-px shrink-0 text-rule-prazo" />
            A IA não identificou uma regra neste trecho. Você ainda pode registrá-lo, se discordar.
          </p>
        )}
        <CategoryToggle value={category} onChange={setCategory} />
        {proposal.reason && <p className="text-xs text-foreground-muted">{proposal.reason}</p>}
      </div>

      <div className="grid gap-3">
        <Field label="Tipo" htmlFor={`${ids}-type`}>
          <RuleTypeSelect id={`${ids}-type`} value={type} onChange={setType} />
        </Field>
        <Field label="Resumo" htmlFor={`${ids}-summary`}>
          <Input id={`${ids}-summary`} value={summary} maxLength={200} onChange={(e) => setSummary(e.target.value)} />
        </Field>
        <Field label="Interpretação" htmlFor={`${ids}-interpretation`} hint="Como a regra deve ser lida; fica registrada com ela.">
          <Textarea
            id={`${ids}-interpretation`}
            rows={3}
            value={interpretation}
            maxLength={4000}
            onChange={(e) => setInterpretation(e.target.value)}
          />
        </Field>
      </div>

      {category === "csv" &&
        (datasets.length === 0 ? (
          <p className="text-[13px] text-foreground-muted">Não há bases prontas nesta análise. Registre a regra como geral ou envie um CSV.</p>
        ) : (
          <div className="flex flex-col gap-3 border-t border-border pt-4">
            <h4 className="flex items-center gap-2 text-[13px] font-medium">
              <Database size={14} strokeWidth={1.75} aria-hidden className="text-accent" />
              Busca na base
            </h4>
            <QueryBuilder state={builder} datasets={datasets} compact onEdit={() => setResult(null)} />
            {builder.error && <FormError>{builder.error}</FormError>}
            {result?.error && <FormError>{result.error}</FormError>}
            {result?.sql && (
              <div className="flex flex-col gap-1.5">
                <span className="text-xs text-foreground-subtle">SQL que será executada</span>
                <pre className="max-h-40 overflow-auto rounded-md bg-surface-muted p-2.5 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
                  {result.sql}
                </pre>
              </div>
            )}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p role="status" className="text-[13px] text-foreground-muted tabular-nums">
                {result?.count != null
                  ? `${result.count.toLocaleString("pt-BR")} ${result.count === 1 ? "registro encontrado" : "registros encontrados"}`
                  : "Teste a busca para ver quantos registros ela encontra."}
              </p>
              <Button size="sm" icon={<Play size={14} strokeWidth={1.75} aria-hidden />} loading={preview.isPending} onClick={test}>
                Testar busca
              </Button>
            </div>
          </div>
        ))}

      {error && <FormError>{error}</FormError>}
    </section>
  );
}

const CATEGORIES: { value: RuleCategory; label: string; hint: string }[] = [
  { value: "csv", label: "Verificável no CSV", hint: "Vira uma busca nas bases" },
  { value: "geral", label: "Regra geral", hint: "Fica registrada sem busca" },
];

function CategoryToggle({ value, onChange }: { value: RuleCategory; onChange: (value: RuleCategory) => void }) {
  return (
    <div role="radiogroup" aria-label="Classificação da regra" className="grid grid-cols-2 gap-1 rounded-md bg-surface-muted p-1">
      {CATEGORIES.map((c) => (
        <button
          key={c.value}
          type="button"
          role="radio"
          aria-checked={value === c.value}
          onClick={() => onChange(c.value)}
          className={cn(
            "flex flex-col items-start rounded-sm px-2.5 py-1.5 text-left transition-colors duration-150 ease-out",
            value === c.value ? "bg-surface text-foreground shadow-sm" : "text-foreground-muted hover:text-foreground",
          )}
        >
          <span className="text-[13px] font-medium">{c.label}</span>
          <span className="text-[11px] text-foreground-subtle">{c.hint}</span>
        </button>
      ))}
    </div>
  );
}
