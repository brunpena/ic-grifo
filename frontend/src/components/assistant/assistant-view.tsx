"use client";

import { FileText, FileUp, Library, MousePointerClick, X } from "lucide-react";
import Link from "next/link";
import { type DragEvent, type ReactNode, useRef, useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { BrandLogo } from "@/components/brand-logo";
import { AssistantMessage, UserMessage } from "@/components/chat/chat-message";
import { CreateRulePopover } from "@/components/document/create-rule-popover";
import { HighlightLayer, type PageRect } from "@/components/document/highlight-layer";
import { PDF_TO_CSS, PdfDocumentPages, usePdfDocument } from "@/components/document/pdf-document";
import { PdfPage, PdfViewer } from "@/components/document/pdf-viewer";
import { PdfToolbar } from "@/components/document/pdf-toolbar";
import { RuleLegend } from "@/components/document/rule-legend";
import { RulesHeader } from "@/components/rules/rules-header";
import { RulesTable } from "@/components/rules/rules-table";
import type { RuleView } from "@/components/rules/types";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { IconButton } from "@/components/ui/icon-button";
import { useToast } from "@/components/ui/toast";
import { firstName, useCurrentUser } from "@/lib/auth";
import type { RuleStatus, RuleType } from "@/lib/design/tokens";
import type { FloatingAnchor } from "@/lib/floating";
import { DESKTOP_QUERY, useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { AssistantComposer, AssistantDisclaimer } from "./assistant-composer";

type ChatMessage = { id: string; role: "user" | "assistant"; content: ReactNode };

/** Regra criada nesta tela, com a posição do grifo em cada página. */
type LocalRule = RuleView & { page: number; rects: PageRect[] };

type MobileTab = "chat" | "document" | "rules";

// Ainda não existe API de conversa nem de extração de regras: as respostas abaixo
// explicam isso em vez de simular uma IA. Troque pelos dados do back quando houver.
const CHAT_UNAVAILABLE =
  "Ainda não consigo responder: a conversa com a IA não está ligada ao back-end. Por enquanto, as mensagens ficam só nesta tela.";

let nextId = 0;
const newId = () => `m${++nextId}`;

export function AssistantView() {
  const toast = useToast();
  const { data: user } = useCurrentUser();
  const isDesktop = useMediaQuery(DESKTOP_QUERY);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [viewerWidth, setViewerWidth] = useState(0);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const pdf = usePdfDocument(file);
  // `null` = ajustar à largura do painel (até a pessoa mexer no zoom).
  const [zoomOverride, setZoomOverride] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [rules, setRules] = useState<LocalRule[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [pulse, setPulse] = useState<{ ruleId: string; key: number } | null>(null);
  const [typeFilter, setTypeFilter] = useState<RuleType | null>(null);
  const [statusFilter, setStatusFilter] = useState<RuleStatus | null>(null);
  const [mobileTab, setMobileTab] = useState<MobileTab>("document");
  const [createOpen, setCreateOpen] = useState(false);
  const selectionRef = useRef<FloatingAnchor | null>(null);
  const selectionInfo = useRef<{ page: number; text: string; rects: PageRect[] } | null>(null);

  const openFile = (picked: File | undefined) => {
    if (!picked) return;
    if (picked.type !== "application/pdf" && !picked.name.toLowerCase().endsWith(".pdf")) {
      toast({ title: "Envie um arquivo PDF", description: `“${picked.name}” não é um PDF.`, variant: "error" });
      return;
    }
    setFile(picked);
    setZoomOverride(null);
    setRules([]);
    setSelectedId(null);
    setPage(1);
    setMobileTab("document");
    setMessages((list) => [
      ...list,
      {
        id: newId(),
        role: "assistant",
        content: `Abri “${picked.name}”. Selecione um trecho do documento e use “Criar regra” para marcá-lo. A identificação automática das regras ainda não está ligada ao back-end.`,
      },
    ]);
  };

  const send = () => {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    setMessages((list) => [
      ...list,
      { id: newId(), role: "user", content: text },
      { id: newId(), role: "assistant", content: CHAT_UNAVAILABLE },
    ]);
  };

  const closeDocument = () => {
    setFile(null);
    setRules([]);
    setSelectedId(null);
  };

  // Mede a área do documento para o zoom "ajustar à largura".
  const viewerRef = (el: HTMLDivElement | null) => {
    scrollRef.current = el;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setViewerWidth(entry.contentRect.width));
    observer.observe(el);
    return () => {
      observer.disconnect();
      scrollRef.current = null;
    };
  };

  const scrollToPage = (n: number, rect?: PageRect) => {
    const scroller = scrollRef.current;
    const pageEl = scroller?.querySelector<HTMLElement>(`[data-page="${n}"]`);
    if (!scroller || !pageEl) return;
    const top =
      pageEl.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop +
      (rect ? rect.y * pageEl.offsetHeight : 0) -
      scroller.clientHeight / 3;
    scroller.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  };

  const goToRule = (id: string) => {
    const rule = rules.find((r) => r.id === id);
    if (!rule) return;
    setSelectedId(id);
    setPulse((p) => ({ ruleId: id, key: (p?.key ?? 0) + 1 }));
    if (!isDesktop) setMobileTab("document");
    // Na troca de aba, espera a página aparecer antes de rolar.
    requestAnimationFrame(() => scrollToPage(rule.page, rule.rects[0]));
  };

  const onPageMouseUp = (pageNumber: number, pageEl: HTMLElement) => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !pageEl.contains(sel.anchorNode)) return;
    const text = sel.toString().replace(/\s+/g, " ").trim();
    if (!text) return;
    const range = sel.getRangeAt(0);
    const box = pageEl.getBoundingClientRect();
    selectionRef.current = range;
    selectionInfo.current = {
      page: pageNumber,
      text,
      rects: Array.from(range.getClientRects())
        .filter((r) => r.width > 0 && r.height > 0)
        .map((r) => ({
          x: (r.left - box.left) / box.width,
          y: (r.top - box.top) / box.height,
          width: r.width / box.width,
          height: r.height / box.height,
        })),
    };
    setCreateOpen(true);
  };

  const onPageClick = (pageNumber: number, point: { x: number; y: number }) => {
    const hit = rules.find(
      (r) =>
        r.page === pageNumber &&
        r.rects.some((b) => point.x >= b.x && point.x <= b.x + b.width && point.y >= b.y && point.y <= b.y + b.height),
    );
    if (hit) goToRule(hit.id);
  };

  const onScroll = () => {
    const scroller = scrollRef.current;
    if (!scroller) return;
    const line = scroller.getBoundingClientRect().top + scroller.clientHeight / 3;
    let current = 1;
    for (const el of scroller.querySelectorAll<HTMLElement>("[data-page]")) {
      if (el.getBoundingClientRect().top <= line) current = Number(el.dataset.page);
      else break;
    }
    setPage(current);
  };

  const fileInput = (
    <input
      ref={fileInputRef}
      type="file"
      accept="application/pdf,.pdf"
      className="sr-only"
      tabIndex={-1}
      aria-hidden
      onChange={(e) => {
        openFile(e.target.files?.[0]);
        e.target.value = "";
      }}
    />
  );
  const attach = () => fileInputRef.current?.click();

  const dropHandlers = {
    onDragEnter: (e: DragEvent) => {
      if (!e.dataTransfer.types.includes("Files")) return;
      e.preventDefault();
      setDragging(true);
    },
    onDragOver: (e: DragEvent) => {
      if (e.dataTransfer.types.includes("Files")) e.preventDefault();
    },
    onDragLeave: (e: DragEvent) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
    },
    onDrop: (e: DragEvent) => {
      e.preventDefault();
      setDragging(false);
      openFile(e.dataTransfer.files[0]);
    },
  };

  const composer = (
    <AssistantComposer
      value={draft}
      onChange={setDraft}
      onSubmit={send}
      onAttach={attach}
      documentName={file?.name}
      // Com documento aberto, o nome dele já aparece no topo da conversa.
      showDocument={!file}
    />
  );

  // ----- Sem documento: conversa centralizada, no estilo do lineFlow -----
  if (!file) {
    return (
      <div className="relative flex h-full flex-col" {...dropHandlers}>
        {fileInput}
        <Glow />
        <div className="relative flex items-center gap-2 px-6 pt-6">
          <span className="text-base font-semibold">Grifo IA</span>
          <span className="rounded-full border border-accent/40 px-2 py-0.5 text-[11px] font-medium text-accent">Beta</span>
        </div>

        {messages.length === 0 ? (
          <div className="relative flex flex-1 flex-col items-center justify-center gap-4 px-4 text-center">
            <h1 className="text-[28px] leading-tight font-medium tracking-tight sm:text-[38px]">
              Pronto para validar, {user ? firstName(user.name) : ""}?
            </h1>
            <p className="max-w-md text-sm text-foreground-muted">
              Envie um contrato, edital ou regulamento. O documento abre ao lado da conversa, com as regras grifadas.
            </p>
            <div className="mt-2 flex flex-wrap justify-center gap-2">
              <Button size="sm" variant="primary" icon={<FileUp size={16} strokeWidth={1.75} aria-hidden />} onClick={attach} className="rounded-full">
                Enviar um PDF
              </Button>
              <Link
                href="/regras"
                className="inline-flex h-8 items-center gap-2 rounded-full border border-border-strong bg-surface px-3 text-[13px] font-medium transition-colors duration-150 ease-out hover:bg-surface-hover"
              >
                <Library size={16} strokeWidth={1.75} aria-hidden />
                Ver base de regras
              </Link>
            </div>
          </div>
        ) : (
          <ChatThread messages={messages} className="relative mx-auto w-full max-w-3xl flex-1 px-4 py-6" />
        )}

        <div className="relative mx-auto w-full max-w-3xl px-4 pb-4">
          {composer}
          <AssistantDisclaimer className="mt-2" />
        </div>
        {dragging && <DropOverlay />}
      </div>
    );
  }

  // ----- Com documento: conversa, documento e regras -----
  const visibleRules = rules.filter(
    (r) => (!typeFilter || r.type === typeFilter) && (!statusFilter || r.status === statusFilter),
  );
  const activeRuleId = hoverId ?? selectedId;
  const widestPage = pdf.status === "ready" ? Math.max(...pdf.pages.map((p) => p.width)) : 595;
  // Arredondado em passos de 5% para não redesenhar as páginas a cada pixel ao arrastar a divisória.
  const fitZoom = viewerWidth
    ? Math.min(2, Math.max(0.5, Math.floor(((viewerWidth - 32) / (widestPage * PDF_TO_CSS)) * 20) / 20))
    : 1;
  const zoom = zoomOverride ?? fitZoom;

  const chatPanel = (
    <section aria-label="Conversa" className="flex h-full min-h-0 flex-col bg-background">
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-3">
        <FileText size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-accent" />
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{file.name}</span>
        {pdf.status === "ready" && (
          <span className="shrink-0 font-mono text-xs text-foreground-subtle tabular-nums">{pdf.pages.length} p.</span>
        )}
        <IconButton aria-label="Fechar documento" icon={<X size={16} strokeWidth={1.75} aria-hidden />} onClick={closeDocument} />
      </div>
      <ChatThread messages={messages} className="flex-1 px-4 py-5" />
      <div className="shrink-0 p-3">
        {composer}
        <AssistantDisclaimer className="mt-2" />
      </div>
    </section>
  );

  const documentPanel = (
    <PdfViewer
      scrollRef={viewerRef}
      onScroll={onScroll}
      header={
        <>
          <PdfToolbar
            zoom={zoom}
            onZoomIn={() => setZoomOverride(Math.min(3, +(zoom + 0.1).toFixed(2)))}
            onZoomOut={() => setZoomOverride(Math.max(0.5, +(zoom - 0.1).toFixed(2)))}
            onZoomReset={() => setZoomOverride(1)}
            page={page}
            pageCount={pdf.status === "ready" ? pdf.pages.length : 0}
          />
          <RuleLegend active={typeFilter} onChange={setTypeFilter} />
        </>
      }
    >
      {pdf.status === "error" ? (
        <EmptyState icon={FileText} title="Não foi possível abrir" description={pdf.message} className="mt-16" />
      ) : pdf.status === "ready" ? (
        <PdfDocumentPages
          doc={pdf.doc}
          pages={pdf.pages}
          zoom={zoom}
          onPageMouseUp={onPageMouseUp}
          onPageClick={onPageClick}
          renderOverlay={(n) => (
            <HighlightLayer
              highlights={rules
                .filter((r) => r.page === n)
                .map((r) => ({ ruleId: r.id, type: r.type, status: r.status, rects: r.rects }))}
              activeRuleId={activeRuleId}
              pulse={pulse}
            />
          )}
        />
      ) : (
        // Proporção de uma folha A4 enquanto o PDF abre.
        [1, 2].map((n) => <PdfPage key={n} pageNumber={n} width={595 * zoom * PDF_TO_CSS} height={842 * zoom * PDF_TO_CSS} loading />)
      )}
    </PdfViewer>
  );

  const rulesPanel = (
    <section aria-label="Regras" className="flex h-full min-h-0 flex-col bg-surface">
      <RulesHeader
        validated={rules.filter((r) => r.status === "validada").length}
        total={rules.length}
        typeFilter={typeFilter}
        onTypeFilterChange={setTypeFilter}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
      />
      <RulesTable
        className="flex-1"
        rules={visibleRules}
        selectedId={selectedId}
        onSelect={(r) => goToRule(r.id)}
        onHover={(r) => setHoverId(r?.id ?? null)}
        onSetStatus={(rule, status) => setRules((list) => list.map((r) => (r.id === rule.id ? { ...r, status } : r)))}
        empty={
          rules.length === 0 ? (
            <EmptyState
              icon={MousePointerClick}
              title="Nenhuma regra ainda"
              description="Selecione um trecho do documento e clique em “Criar regra”."
            />
          ) : undefined
        }
      />
    </section>
  );

  return (
    <div className="relative h-full" {...dropHandlers}>
      {fileInput}
      {isDesktop ? (
        <Group orientation="horizontal" className="h-full">
          <Panel defaultSize="26" minSize={300}>
            {chatPanel}
          </Panel>
          <ResizeHandle />
          <Panel defaultSize="40" minSize={360}>
            {documentPanel}
          </Panel>
          <ResizeHandle />
          <Panel defaultSize="34" minSize={340}>
            {rulesPanel}
          </Panel>
        </Group>
      ) : (
        <div className="flex h-full flex-col">
          <MobileTabs value={mobileTab} onChange={setMobileTab} ruleCount={rules.length} />
          <div className="min-h-0 flex-1">
            {mobileTab === "chat" ? chatPanel : mobileTab === "document" ? documentPanel : rulesPanel}
          </div>
        </div>
      )}

      <CreateRulePopover
        open={createOpen}
        onOpenChange={setCreateOpen}
        anchorRef={selectionRef}
        onCreate={({ type, summary }) => {
          const info = selectionInfo.current;
          if (!info) return;
          const id = `r${Date.now()}`;
          setRules((list) => [
            ...list,
            { id, type, summary, status: "pendente", page: info.page, excerpt: info.text, rects: info.rects },
          ]);
          setCreateOpen(false);
          setSelectedId(id);
          window.getSelection()?.removeAllRanges();
          toast({ title: "Regra criada", description: "Ela fica salva só nesta tela por enquanto.", variant: "success" });
        }}
      />
      {dragging && <DropOverlay />}
    </div>
  );
}

function ChatThread({ messages, className }: { messages: ChatMessage[]; className?: string }) {
  return (
    <div role="log" aria-label="Mensagens" className={cn("flex min-h-0 flex-col gap-5 overflow-auto", className)}>
      {messages.length === 0 && (
        <p className="m-auto max-w-64 text-center text-[13px] text-foreground-subtle">
          Pergunte sobre o documento ou selecione um trecho para criar uma regra.
        </p>
      )}
      {messages.map((m) =>
        m.role === "user" ? <UserMessage key={m.id}>{m.content}</UserMessage> : <AssistantMessage key={m.id}>{m.content}</AssistantMessage>,
      )}
    </div>
  );
}

/** Brilho do azul da marca no centro da tela vazia (mais forte no escuro). */
function Glow() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_55%_50%_at_50%_45%,rgb(10_132_255/0.07),transparent_70%)] dark:bg-[radial-gradient(ellipse_55%_50%_at_50%_45%,rgb(10_132_255/0.15),transparent_70%)]"
    />
  );
}

function DropOverlay() {
  return (
    <div className="pointer-events-none absolute inset-3 z-30 flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-accent bg-accent-soft/80 backdrop-blur-sm">
      <BrandLogo size={40} />
      <p className="text-sm font-medium">Solte o PDF para abrir</p>
    </div>
  );
}

/** Divisória de 1 px com área de clique de 8 px; fica em `accent` no hover e ao arrastar. */
function ResizeHandle() {
  return (
    <Separator
      className={cn(
        "relative w-px bg-border outline-none transition-colors duration-150 ease-out",
        "after:absolute after:inset-y-0 after:-left-1 after:w-2 after:content-['']",
        "data-[separator=active]:bg-accent data-[separator=hover]:bg-accent focus-visible:bg-accent",
      )}
    />
  );
}

const TABS: { value: MobileTab; label: string }[] = [
  { value: "chat", label: "Conversa" },
  { value: "document", label: "Documento" },
  { value: "rules", label: "Regras" },
];

function MobileTabs({ value, onChange, ruleCount }: { value: MobileTab; onChange: (tab: MobileTab) => void; ruleCount: number }) {
  return (
    <div role="tablist" aria-label="Painéis" className="flex h-11 shrink-0 border-b border-border bg-surface px-2">
      {TABS.map((tab) => (
        <button
          key={tab.value}
          type="button"
          role="tab"
          aria-selected={value === tab.value}
          onClick={() => onChange(tab.value)}
          className={cn(
            "relative flex flex-1 items-center justify-center gap-1.5 text-[13px] font-medium text-foreground-muted transition-colors duration-150 ease-out",
            value === tab.value && "text-foreground",
          )}
        >
          {tab.label}
          {tab.value === "rules" && ruleCount > 0 && (
            <span className="rounded-full bg-surface-muted px-1.5 font-mono text-[11px] tabular-nums">{ruleCount}</span>
          )}
          {value === tab.value && <span aria-hidden className="bg-brand-gradient absolute inset-x-3 bottom-0 h-0.5 rounded-full" />}
        </button>
      ))}
    </div>
  );
}
