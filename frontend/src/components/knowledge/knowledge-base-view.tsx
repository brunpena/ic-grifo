"use client";

import { CircleCheck, CircleDashed, FileText, FlaskConical, type LucideIcon } from "lucide-react";
import { useState } from "react";
import type { CitedRule } from "@/components/chat/chat-message";
import { RulesFilterNotice, RulesHeader } from "@/components/rules/rules-header";
import { RulesTable } from "@/components/rules/rules-table";
import { Card } from "@/components/ui/card";
import { DEMO_DOCUMENTS, DEMO_KB_RULES, type DemoKbRule } from "@/lib/demo/knowledge-base";
import type { RuleStatus, RuleType } from "@/lib/design/tokens";
import { msg, type Translate, useT } from "@/lib/i18n";
import { AnswerCard } from "./answer-card";
import { QuestionBar } from "./question-bar";

const normalize = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** Busca simples por palavras, só para a demonstração (a real será semântica, no back). */
function answerFor(question: string, rules: DemoKbRule[], t: Translate) {
  const words = normalize(question)
    .split(/[^a-z0-9%]+/)
    .filter((w) => w.length > 3);
  const cited = rules.filter(
    (r) => r.status === "validada" && words.some((w) => normalize(`${r.summary} ${r.excerpt}`).includes(w)),
  );
  const sources = cited
    .slice(0, 3)
    .map((r) => t("{summary} ({document}, p. {page})", { summary: r.summary, document: r.document, page: r.page ?? "—" }))
    .join("; ");
  const text = cited.length
    ? t.plural(
        cited.length,
        "Encontrei {n} regra validada sobre o tema. {sources}.",
        "Encontrei {n} regras validadas sobre o tema. {sources}.",
        { sources },
      )
    : t("Não encontrei regras validadas sobre esse tema. Tente outras palavras, como “prazo”, “multa” ou “pagamento”.");
  return { text, cited };
}

export function KnowledgeBaseView() {
  const t = useT();
  const [rules, setRules] = useState(DEMO_KB_RULES);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState<{ question: string; text: string; cited: DemoKbRule[] } | null>(null);
  const [answerFilter, setAnswerFilter] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<RuleType | null>(null);
  const [statusFilter, setStatusFilter] = useState<RuleStatus | null>(null);

  const ask = () => {
    const q = question.trim();
    setLoading(true);
    window.setTimeout(() => {
      const result = answerFor(q, rules, t);
      setAnswer({ question: q, ...result });
      setAnswerFilter(result.cited.length > 0);
      setLoading(false);
    }, 600);
  };

  const citedIds = new Set(answer?.cited.map((r) => r.id));
  const visible = rules.filter(
    (r) =>
      (!typeFilter || r.type === typeFilter) &&
      (!statusFilter || r.status === statusFilter) &&
      (!answerFilter || citedIds.has(r.id)),
  );
  const validated = rules.filter((r) => r.status === "validada").length;
  const citations: CitedRule[] = answer?.cited.map(({ id, type, summary }) => ({ id, type, summary })) ?? [];

  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 pt-8 pb-12 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold">{t("Base de regras")}</h1>
            <p className="text-[13px] text-foreground-muted">
              {t("Todas as regras dos seus documentos. Pergunte em linguagem natural para encontrar a que você precisa.")}
            </p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs text-foreground-muted">
            <FlaskConical size={14} strokeWidth={1.75} aria-hidden className="text-accent" />
            {t("Dados de exemplo")}
          </span>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <Stat icon={CircleCheck} label={msg("Regras validadas")} value={validated} />
          <Stat icon={CircleDashed} label={msg("Aguardando revisão")} value={rules.filter((r) => r.status === "pendente").length} />
          <Stat icon={FileText} label={msg("Documentos")} value={DEMO_DOCUMENTS.length} />
        </div>

        <div className="flex flex-col gap-3">
          <QuestionBar value={question} onChange={setQuestion} onSubmit={ask} loading={loading} />
          {answer && (
            <AnswerCard
              key={answer.question}
              question={answer.question}
              citations={citations}
              onCitationClick={(id) => {
                setSelectedId(id);
                setAnswerFilter(true);
              }}
            >
              {answer.text}
            </AnswerCard>
          )}
        </div>

        <Card className="flex h-[560px] flex-col overflow-hidden p-0">
          <RulesHeader
            validated={validated}
            total={rules.length}
            typeFilter={typeFilter}
            onTypeFilterChange={setTypeFilter}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
          />
          {answerFilter && answer && (
            <RulesFilterNotice count={answer.cited.length} onShowAll={() => setAnswerFilter(false)} />
          )}
          <RulesTable
            className="flex-1"
            rules={visible}
            selectedId={selectedId}
            onSelect={(r) => setSelectedId(r.id)}
            onSetStatus={(rule, status) => setRules((list) => list.map((r) => (r.id === rule.id ? { ...r, status } : r)))}
          />
        </Card>
      </div>
    </div>
  );
}

/** `label` em português; traduzido ao exibir. */
function Stat({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: number }) {
  const t = useT();
  return (
    <Card className="flex items-center gap-3">
      <span className="inline-flex size-9 items-center justify-center rounded-md bg-accent-soft text-accent">
        <Icon size={18} strokeWidth={1.75} aria-hidden />
      </span>
      <div className="flex flex-col">
        <span className="text-xl font-semibold tabular-nums">{t.number(value)}</span>
        <span className="text-xs text-foreground-subtle">{t(label)}</span>
      </div>
    </Card>
  );
}
