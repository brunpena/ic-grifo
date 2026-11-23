"use client";

import { Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AssistantMessage, type CitedRule, UserMessage } from "@/components/chat/chat-message";
import { ChatComposer } from "@/components/chat/chat-composer";
import { ProcessingSteps, PROCESSING_STEPS } from "@/components/chat/processing-steps";
import { UploadDropzone } from "@/components/chat/upload-dropzone";
import { CreateRulePopover } from "@/components/document/create-rule-popover";
import { HighlightLayer, type PageRect, type RuleHighlight } from "@/components/document/highlight-layer";
import { PdfPage, PdfViewer } from "@/components/document/pdf-viewer";
import { PdfToolbar } from "@/components/document/pdf-toolbar";
import { RuleLegend } from "@/components/document/rule-legend";
import { SearchBar } from "@/components/document/search-bar";
import { AnswerCard } from "@/components/knowledge/answer-card";
import { QuestionBar } from "@/components/knowledge/question-bar";
import { RulesFilterNotice, RulesHeader } from "@/components/rules/rules-header";
import { RulesTable } from "@/components/rules/rules-table";
import type { RuleView } from "@/components/rules/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import type { RuleStatus, RuleType } from "@/lib/design/tokens";
import type { FloatingAnchor } from "@/lib/floating";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Dados de exemplo (existem só nesta página)
// ---------------------------------------------------------------------------

const PAGE_W = 420;
const PAGE_H = 594;
const WRAP = 64;

const PAGES_TEXT = [
  [
    "CLÁUSULA PRIMEIRA – DO OBJETO",
    "O presente contrato tem por objeto a prestação de serviços de manutenção preventiva e corretiva dos equipamentos de climatização do edifício-sede, conforme especificações do Termo de Referência.",
    "CLÁUSULA SEGUNDA – DAS OBRIGAÇÕES DA CONTRATADA",
    "A contratada deverá entregar o relatório mensal de atividades em até 10 dias úteis após o encerramento de cada mês de execução.",
    "É vedada a subcontratação total ou parcial do objeto sem prévia autorização por escrito da contratante.",
    "A contratada deverá manter, durante toda a execução, as condições de habilitação exigidas na licitação.",
  ],
  [
    "CLÁUSULA TERCEIRA – DOS PRAZOS",
    "O prazo de vigência do contrato é de 12 meses, contados da data de sua assinatura, podendo ser prorrogado nos termos da lei.",
    "Caso haja atraso injustificado na execução, será aplicada multa de 0,5% ao dia sobre o valor da parcela em atraso.",
    "CLÁUSULA QUARTA – DO PAGAMENTO",
    "O pagamento será efetuado em até 30 dias após o atesto da nota fiscal pelo fiscal do contrato.",
    "Os casos omissos serão resolvidos pela contratante, com base na legislação vigente.",
  ],
];

/** Quebra os parágrafos em linhas; uma linha vazia separa os parágrafos. */
function wrap(paragraphs: string[]) {
  const lines: string[] = [];
  for (const p of paragraphs) {
    let line = "";
    for (const word of p.split(" ")) {
      if (line && line.length + 1 + word.length > WRAP) {
        lines.push(line);
        line = word;
      } else line = line ? `${line} ${word}` : word;
    }
    lines.push(line, "");
  }
  return lines;
}

const PAGES = PAGES_TEXT.map(wrap);

type Span = { line: number; from: number; to: number };

/** Localiza um trecho nas linhas de uma página (pode atravessar linhas). */
function spansOf(lines: string[], phrase: string): Span[] {
  const starts: number[] = [];
  let offset = 0;
  for (const l of lines) {
    starts.push(offset);
    offset += l.length + 1;
  }
  const s = lines.join(" ").indexOf(phrase);
  if (s < 0) return [];
  const e = s + phrase.length;
  return lines.flatMap((l, i) => {
    const from = Math.max(s, starts[i]);
    const to = Math.min(e, starts[i] + l.length);
    return to > from ? [{ line: i, from: from - starts[i], to: to - starts[i] }] : [];
  });
}

type DemoRule = RuleView & { page: number; spans: Span[]; rects?: PageRect[] };

const RULE_SEEDS: { type: RuleType; status: RuleStatus; page: number; phrase: string; summary: string }[] = [
  { type: "obrigacao", status: "validada", page: 1, phrase: "A contratada deverá entregar o relatório mensal de atividades", summary: "Entregar relatório mensal de atividades" },
  { type: "prazo", status: "pendente", page: 1, phrase: "em até 10 dias úteis após o encerramento de cada mês", summary: "Relatório em até 10 dias úteis" },
  { type: "proibicao", status: "pendente", page: 1, phrase: "É vedada a subcontratação total ou parcial do objeto", summary: "Proibida a subcontratação sem autorização" },
  { type: "obrigacao", status: "rejeitada", page: 1, phrase: "manter, durante toda a execução, as condições de habilitação", summary: "Manter condições de habilitação" },
  { type: "prazo", status: "validada", page: 2, phrase: "O prazo de vigência do contrato é de 12 meses", summary: "Vigência de 12 meses" },
  { type: "condicao", status: "pendente", page: 2, phrase: "Caso haja atraso injustificado na execução", summary: "Multa em caso de atraso injustificado" },
  { type: "obrigacao", status: "pendente", page: 2, phrase: "O pagamento será efetuado em até 30 dias após o atesto", summary: "Pagamento em até 30 dias do atesto" },
  { type: "outro", status: "pendente", page: 2, phrase: "Os casos omissos serão resolvidos pela contratante", summary: "Casos omissos resolvidos pela contratante" },
];

const INITIAL_RULES: DemoRule[] = RULE_SEEDS.map((r, i) => ({
  id: `r${i + 1}`,
  type: r.type,
  status: r.status,
  page: r.page,
  summary: r.summary,
  excerpt: r.phrase,
  spans: spansOf(PAGES[r.page - 1], r.phrase),
}));

// ---------------------------------------------------------------------------
// Medição dos retângulos a partir do texto renderizado (como fará o pdf.js)
// ---------------------------------------------------------------------------

function toPageRect(rect: DOMRect, page: DOMRect): PageRect {
  return {
    x: (rect.left - page.left) / page.width,
    y: (rect.top - page.top) / page.height,
    width: rect.width / page.width,
    height: rect.height / page.height,
  };
}

function measureSpans(pageEl: Element, spans: Span[]): PageRect[] {
  const box = pageEl.getBoundingClientRect();
  return spans.flatMap(({ line, from, to }) => {
    const node = pageEl.querySelector(`[data-line="${line}"]`)?.firstChild;
    if (!node) return [];
    const range = document.createRange();
    range.setStart(node, from);
    range.setEnd(node, to);
    return [toPageRect(range.getBoundingClientRect(), box)];
  });
}

type SearchMatch = { page: number; rect: PageRect };

function findMatches(root: HTMLElement, query: string): SearchMatch[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return PAGES.flatMap((lines, p) => {
    const pageEl = root.querySelector(`[data-page="${p + 1}"]`);
    if (!pageEl) return [];
    return lines.flatMap((line, i) => {
      const spans: Span[] = [];
      for (let at = line.toLowerCase().indexOf(q); at >= 0; at = line.toLowerCase().indexOf(q, at + q.length)) {
        spans.push({ line: i, from: at, to: at + q.length });
      }
      return measureSpans(pageEl, spans).map((rect) => ({ page: p + 1, rect }));
    });
  });
}

// ---------------------------------------------------------------------------

export function SystemDemo() {
  return (
    <div className="flex flex-col gap-8">
      <WorkspaceDemo />
      <div className="grid gap-4 lg:grid-cols-2">
        <ChatDemo />
        <div className="flex flex-col gap-4">
          <ProcessingDemo />
          <KnowledgeDemo />
        </div>
      </div>
    </div>
  );
}

function WorkspaceDemo() {
  const toast = useToast();
  const workspaceRef = useRef<HTMLDivElement>(null);
  const [rules, setRules] = useState(INITIAL_RULES);
  const [zoom, setZoom] = useState(1);
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [pulse, setPulse] = useState<{ ruleId: string; key: number } | null>(null);
  const [typeFilter, setTypeFilter] = useState<RuleType | null>(null);
  const [statusFilter, setStatusFilter] = useState<RuleStatus | null>(null);
  const [answerFilter, setAnswerFilter] = useState<Set<string> | null>(null);
  const [tableLoading, setTableLoading] = useState(false);
  const [pagesLoading, setPagesLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<SearchMatch[]>([]);
  const [current, setCurrent] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const selectionRef = useRef<FloatingAnchor | null>(null);
  const selectionInfo = useRef<{ page: number; text: string; rects: PageRect[] } | null>(null);

  // Mede os grifos depois que as fontes carregam (as frações não dependem do zoom).
  useEffect(() => {
    let alive = true;
    document.fonts.ready.then(() => {
      const root = workspaceRef.current;
      if (!alive || !root) return;
      setRules((list) =>
        list.map((r) => {
          const pageEl = root.querySelector(`[data-page="${r.page}"]`);
          return pageEl && !r.rects ? { ...r, rects: measureSpans(pageEl, r.spans) } : r;
        }),
      );
    });
    return () => {
      alive = false;
    };
  }, []);

  const visible = rules.filter(
    (r) =>
      (!typeFilter || r.type === typeFilter) &&
      (!statusFilter || r.status === statusFilter) &&
      (!answerFilter || answerFilter.has(r.id)),
  );

  const goToRule = (id: string) => {
    const rule = rules.find((r) => r.id === id);
    if (!rule) return;
    setSelectedId(id);
    setPulse((p) => ({ ruleId: id, key: (p?.key ?? 0) + 1 }));
    scrollToPage(rule.page, rule.rects?.[0]);
  };

  const scrollToPage = (n: number, rect?: PageRect) => {
    setPage(n);
    const pageEl = workspaceRef.current?.querySelector<HTMLElement>(`[data-page="${n}"]`);
    const scroller = pageEl?.closest<HTMLElement>(".overflow-auto");
    if (!pageEl || !scroller) return;
    const y = pageEl.offsetTop + (rect ? rect.y * pageEl.offsetHeight : 0) - scroller.clientHeight / 3;
    scroller.scrollTo({ top: Math.max(0, y), behavior: "smooth" });
  };

  const runSearch = (q: string) => {
    setQuery(q);
    const found = workspaceRef.current ? findMatches(workspaceRef.current, q) : [];
    setMatches(found);
    setCurrent(0);
    if (found[0]) scrollToPage(found[0].page, found[0].rect);
  };

  const step = (delta: number) => {
    if (matches.length === 0) return;
    const next = (current + delta + matches.length) % matches.length;
    setCurrent(next);
    scrollToPage(matches[next].page, matches[next].rect);
  };

  const setStatus = (rule: RuleView, status: RuleStatus) =>
    setRules((list) => list.map((r) => (r.id === rule.id ? { ...r, status } : r)));

  const onPageMouseUp = (pageNumber: number, pageEl: HTMLElement) => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !pageEl.contains(sel.anchorNode)) return;
    const range = sel.getRangeAt(0);
    const box = pageEl.getBoundingClientRect();
    selectionRef.current = range;
    selectionInfo.current = {
      page: pageNumber,
      text: sel.toString().replace(/\s+/g, " ").trim(),
      rects: Array.from(range.getClientRects()).map((r) => toPageRect(r, box)),
    };
    setCreateOpen(true);
  };

  const activeRuleId = hoverId ?? selectedId;
  const validated = rules.filter((r) => r.status === "validada").length;

  return (
    <section className="flex flex-col gap-3" aria-label="Workspace de exemplo">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-sm font-semibold">Workspace (documento e regras)</h2>
        <Button size="sm" onClick={() => setTableLoading((v) => !v)}>
          {tableLoading ? "Mostrar regras" : "Tabela carregando"}
        </Button>
        <Button size="sm" onClick={() => setPagesLoading((v) => !v)}>
          {pagesLoading ? "Mostrar páginas" : "Páginas carregando"}
        </Button>
        <Button size="sm" onClick={() => setAnswerFilter((f) => (f ? null : new Set(["r1", "r2", "r5", "r7"])))}>
          {answerFilter ? "Sem filtro da resposta" : "Filtro da resposta"}
        </Button>
      </div>
      <p className="text-[13px] text-foreground-muted">
        Selecione um trecho da página para criar uma regra. Ctrl+F (com o foco no workspace) abre a busca.
        Clique numa linha da tabela para navegar até a regra.
      </p>

      <div
        ref={workspaceRef}
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
            e.preventDefault();
            setSearchOpen(true);
          }
        }}
        className="grid h-[640px] overflow-hidden rounded-lg border border-border lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]"
      >
        <PdfViewer
          className="border-border max-lg:h-[640px] lg:border-r"
          header={
            <>
              <PdfToolbar
                zoom={zoom}
                onZoomIn={() => setZoom((z) => Math.min(3, +(z + 0.1).toFixed(2)))}
                onZoomOut={() => setZoom((z) => Math.max(0.5, +(z - 0.1).toFixed(2)))}
                onZoomReset={() => setZoom(1)}
                page={page}
                pageCount={PAGES.length}
                exporting={exporting}
                onExport={() => {
                  setExporting(true);
                  window.setTimeout(() => {
                    setExporting(false);
                    toast({ title: "PDF exportado", variant: "success" });
                  }, 1200);
                }}
              />
              <RuleLegend active={typeFilter} onChange={setTypeFilter} />
            </>
          }
          overlay={
            searchOpen ? (
              <SearchBar
                className="absolute top-3 right-3 z-20"
                query={query}
                onQueryChange={runSearch}
                current={current}
                total={matches.length}
                onPrevious={() => step(-1)}
                onNext={() => step(1)}
                onClose={() => {
                  setSearchOpen(false);
                  runSearch("");
                }}
              />
            ) : (
              <Button
                size="sm"
                icon={<Search size={16} strokeWidth={1.75} aria-hidden />}
                className="absolute top-3 right-3 z-20 shadow-sm"
                onClick={() => setSearchOpen(true)}
              >
                Buscar
              </Button>
            )
          }
        >
          {PAGES.map((lines, p) => {
            const n = p + 1;
            const highlights: RuleHighlight[] = rules
              .filter((r) => r.page === n && r.rects)
              .map((r) => ({ ruleId: r.id, type: r.type, status: r.status, rects: r.rects! }));
            const pageMatches = matches.map((m, i) => ({ ...m, i })).filter((m) => m.page === n);
            return (
              <PdfPage key={n} pageNumber={n} width={PAGE_W * zoom} height={PAGE_H * zoom} loading={pagesLoading}>
                <div
                  className="absolute inset-0 origin-top-left text-[10.5px] text-[#1f2937]"
                  style={{ zoom, fontFamily: "Georgia, 'Times New Roman', serif" }}
                  onMouseUp={(e) => onPageMouseUp(n, e.currentTarget.parentElement!)}
                >
                  {lines.map((line, i) => (
                    <div
                      key={i}
                      data-line={i}
                      className={cn("absolute left-11 whitespace-pre", line.startsWith("CLÁUSULA") && "font-bold")}
                      style={{ top: 48 + i * 17 }}
                    >
                      {line}
                    </div>
                  ))}
                  <div className="absolute right-11 bottom-6 font-mono text-[9px] text-[#6b7280]">{n}</div>
                </div>
                <HighlightLayer
                  highlights={highlights}
                  activeRuleId={activeRuleId}
                  pulse={pulse}
                  searchRects={pageMatches.map((m) => m.rect)}
                  currentSearchIndex={pageMatches.findIndex((m) => m.i === current)}
                  onHoverRule={setHoverId}
                  onClickRule={goToRule}
                />
              </PdfPage>
            );
          })}
        </PdfViewer>

        <section aria-label="Regras" className="flex min-h-0 flex-col bg-surface max-lg:h-[640px]">
          <RulesHeader
            validated={validated}
            total={rules.length}
            typeFilter={typeFilter}
            onTypeFilterChange={setTypeFilter}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
          />
          {answerFilter && <RulesFilterNotice count={answerFilter.size} onShowAll={() => setAnswerFilter(null)} />}
          <RulesTable
            className="flex-1"
            rules={visible}
            loading={tableLoading}
            selectedId={selectedId}
            onSelect={(r) => goToRule(r.id)}
            onHover={(r) => setHoverId(r?.id ?? null)}
            onSetStatus={setStatus}
          />
        </section>
      </div>

      <CreateRulePopover
        open={createOpen}
        onOpenChange={setCreateOpen}
        anchorRef={selectionRef}
        onCreate={({ type, summary }) => {
          const info = selectionInfo.current;
          if (!info) return;
          const id = `n${Date.now()}`;
          setRules((list) => [
            ...list,
            { id, type, summary, status: "pendente", page: info.page, excerpt: info.text, spans: [], rects: info.rects },
          ]);
          setCreateOpen(false);
          window.getSelection()?.removeAllRanges();
          toast({ title: "Regra criada", variant: "success" });
        }}
      />
    </section>
  );
}

const CITED: CitedRule[] = INITIAL_RULES.filter((r) => ["r1", "r2", "r3"].includes(r.id)).map(
  ({ id, type, summary }) => ({ id, type, summary }),
);

function ChatDemo() {
  const [message, setMessage] = useState("");
  const [streaming, setStreaming] = useState(true);
  return (
    <Card className="flex h-[560px] flex-col gap-0 p-0">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <h2 className="text-sm font-semibold">Conversa</h2>
        <Button size="sm" variant="ghost" onClick={() => setStreaming((v) => !v)}>
          {streaming ? "Parar streaming" : "Simular streaming"}
        </Button>
      </div>
      <div role="log" aria-label="Conversa" className="flex min-h-0 flex-1 flex-col gap-5 overflow-auto p-4">
        <UserMessage>Quais são as obrigações da contratada sobre relatórios?</UserMessage>
        <AssistantMessage citations={CITED}>
          A contratada deve entregar um relatório mensal de atividades em até 10 dias úteis após o fim de cada mês.
          Não pode subcontratar o objeto sem autorização por escrito.
        </AssistantMessage>
        <UserMessage>E o prazo de vigência?</UserMessage>
        <AssistantMessage streaming={streaming}>O contrato vale por 12 meses a partir da assinatura</AssistantMessage>
      </div>
      <div className="border-t border-border p-3">
        <ChatComposer value={message} onChange={setMessage} onSubmit={() => setMessage("")} onAttach={() => {}} />
      </div>
    </Card>
  );
}

function ProcessingDemo() {
  const [stepIndex, setStepIndex] = useState(1);
  const [failed, setFailed] = useState(false);
  return (
    <Card className="flex flex-col gap-4">
      <h2 className="text-sm font-semibold">Envio e processamento</h2>
      <UploadDropzone onFile={() => setStepIndex(0)} onPasteText={() => {}} />
      <div className="flex flex-wrap items-start justify-between gap-4">
        <ProcessingSteps current={stepIndex} failed={failed} />
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => {
              setFailed(false);
              setStepIndex((i) => (i >= PROCESSING_STEPS.length - 1 ? 0 : i + 1));
            }}
          >
            Avançar etapa
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setFailed((v) => !v)}>
            {failed ? "Sem erro" : "Simular erro"}
          </Button>
        </div>
      </div>
    </Card>
  );
}

function KnowledgeDemo() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold">Base de regras</h2>
      <QuestionBar
        value={question}
        onChange={setQuestion}
        loading={loading}
        onSubmit={() => {
          setLoading(true);
          window.setTimeout(() => setLoading(false), 1200);
        }}
      />
      <AnswerCard question="Quais regras falam de prazos de entrega?" citations={CITED}>
        Duas regras validadas tratam do tema: o relatório mensal deve ser entregue em até 10 dias úteis, e o
        pagamento ocorre em até 30 dias após o atesto da nota fiscal.
      </AnswerCard>
    </Card>
  );
}
