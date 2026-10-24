"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  FilePlus,
  FileSearch,
  FileText,
  FileUp,
  Library,
  Link2,
  MousePointerClick,
  PanelLeftClose,
  Search,
  Sparkles,
  Type,
  X,
} from "lucide-react";
import Link from "next/link";
import { type DragEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { AnalysisWorkspace, PanelToggles, useAnalysisLayout } from "@/components/analysis/analysis-workspace";
import { BrandLogo } from "@/components/brand-logo";
import { AssistantMessage, type CitedRule, UserMessage } from "@/components/chat/chat-message";
import { ProcessingSteps } from "@/components/chat/processing-steps";
import { DatasetUploader } from "@/components/datasets/dataset-uploader";
import { DocumentSourceDialog, type DocumentSourceMode } from "@/components/documents/document-source-dialog";
import { CreateRulePopover } from "@/components/document/create-rule-popover";
import { HighlightLayer, type PageRect } from "@/components/document/highlight-layer";
import { PDF_TO_CSS, PdfDocumentPages, usePdfDocument } from "@/components/document/pdf-document";
import { PdfPage, PdfViewer } from "@/components/document/pdf-viewer";
import { PdfToolbar } from "@/components/document/pdf-toolbar";
import { QueryEditorDialog } from "@/components/queries/query-editor-dialog";
import { RecordsPanel } from "@/components/records/records-panel";
import { RuleLegend } from "@/components/document/rule-legend";
import { SearchBar } from "@/components/document/search-bar";
import { usePdfSearch } from "@/components/document/use-pdf-search";
import { RulesHeader } from "@/components/rules/rules-header";
import { RulesTable } from "@/components/rules/rules-table";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { IconButton } from "@/components/ui/icon-button";
import { Select } from "@/components/ui/select";
import { useToast } from "@/components/ui/toast";
import { useAnalysis, useCreateAnalysis } from "@/lib/analyses";
import { errorMessage } from "@/lib/api";
import { firstName, useCurrentUser } from "@/lib/auth";
import type { RuleStatus, RuleType } from "@/lib/design/tokens";
import {
  DOCUMENT_ACCEPT,
  type DocumentInfo,
  invalidateMessages,
  isDocumentFile,
  isPdfFile,
  type Rule,
  streamMessage,
  stripCitations,
  useCreateRule,
  useDocument,
  useDocumentFile,
  useDocuments,
  useMessages,
  useRules,
  useUpdateRule,
  useUploadDocument,
} from "@/lib/documents";
import type { FloatingAnchor } from "@/lib/floating";
import { describeQuery, useGenerateQueries } from "@/lib/queries";
import { DESKTOP_QUERY, useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
import { AssistantComposer, AssistantDisclaimer } from "./assistant-composer";

type ThreadMessage = {
  id: string;
  role: "user" | "assistant";
  content: ReactNode;
  citations?: CitedRule[];
  streaming?: boolean;
};

type MobileTab = "chat" | "document" | "rules" | "table";

let nextId = 0;
const localId = () => `local-${++nextId}`;

/** Retângulos do grifo de uma regra numa página (vindos do back, em frações da página). */
const rectsOn = (rule: Rule, page: number): PageRect[] =>
  rule.boxes.filter((b) => b.page === page).map(({ x, y, width, height }) => ({ x, y, width, height }));

export function AssistantView() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();
  const isDesktop = useMediaQuery(DESKTOP_QUERY);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [viewerWidth, setViewerWidth] = useState(0);

  // Primeiro envio ainda sem resposta: o nome e, se for PDF, o arquivo para já exibir.
  const [pendingUpload, setPendingUpload] = useState<{ name: string; file: File | null } | null>(null);
  const [sourceMode, setSourceMode] = useState<DocumentSourceMode | null>(null);
  // Análise em montagem: as bases vão antes do documento.
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const { data: analysis } = useAnalysis(analysisId);
  const createAnalysis = useCreateAnalysis();
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const upload = useUploadDocument();
  const uploadMore = useUploadDocument();
  const { data: recent } = useDocuments();
  const { data: doc } = useDocument(documentId);
  // Texto, HTML e links viram PDF no back; o PDF exibido vem sempre de lá (ou do cache).
  const documentFile = useDocumentFile(doc);
  const file = documentId ? (documentFile.data ?? null) : (pendingUpload?.file ?? null);
  const documentName = doc?.title ?? pendingUpload?.name ?? "";
  const isOpen = !!documentId || !!pendingUpload;
  const pdf = usePdfDocument(file);
  const [layout, setLayout] = useAnalysisLayout();
  // Busca no documento (Ctrl+F).
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchIndex, setSearchIndex] = useState(0);
  const search = usePdfSearch(pdf.status === "ready" ? pdf.doc : null, searchOpen ? searchQuery : "");
  const ready = doc?.status === "ready";
  const { data: rules = [] } = useRules(documentId, ready);
  const { data: savedMessages = [] } = useMessages(documentId, ready);
  const updateRule = useUpdateRule(documentId ?? "");
  const createRule = useCreateRule(documentId ?? "");
  const generateQueries = useGenerateQueries(documentId ?? "");
  const [editingQueryId, setEditingQueryId] = useState<string | null>(null);
  const datasets = analysis?.datasets ?? [];

  // Mensagens que ainda não estão no servidor (pergunta enviada e resposta chegando).
  const [pending, setPending] = useState<ThreadMessage[]>([]);
  const [notes, setNotes] = useState<ThreadMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  // `null` = ajustar à largura do painel (até a pessoa mexer no zoom).
  const [zoomOverride, setZoomOverride] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [pulse, setPulse] = useState<{ ruleId: string; key: number } | null>(null);
  const [typeFilter, setTypeFilter] = useState<RuleType | null>(null);
  const [statusFilter, setStatusFilter] = useState<RuleStatus | null>(null);
  const [mobileTab, setMobileTab] = useState<MobileTab>("document");
  const [createOpen, setCreateOpen] = useState(false);
  const selectionRef = useRef<FloatingAnchor | null>(null);
  const selectionInfo = useRef<{ page: number; text: string } | null>(null);

  // Ctrl+F (ou ⌘F) abre a busca no documento em vez da busca do navegador.
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen]);

  const resetView = () => {
    setZoomOverride(null);
    setSelectedId(null);
    setPending([]);
    setNotes([]);
    setPage(1);
    setMobileTab("document");
    setSearchIndex(0);
    upload.reset();
  };

  /** Envia os arquivos para a análise atual e abre o primeiro. */
  const openFiles = async (picked: File[]) => {
    const invalid = picked.filter((f) => !isDocumentFile(f));
    if (invalid.length) {
      toast({
        title: "Formato não suportado",
        description: `${invalid.map((f) => `“${f.name}”`).join(", ")}: envie PDF, HTML ou TXT.`,
        variant: "error",
      });
    }
    const [first, ...rest] = picked.filter(isDocumentFile);
    if (!first) return;
    let target: string;
    try {
      target = await ensureAnalysis();
    } catch (error) {
      toast({ title: "Não foi possível criar a análise", description: errorMessage(error), variant: "error" });
      return;
    }
    setPendingUpload({ name: first.name, file: isPdfFile(first) ? first : null });
    setDocumentId(null);
    resetView();
    upload.mutate(
      { file: first, analysisId: target },
      {
        onSuccess: (created) => {
          setDocumentId(created.id);
          setPendingUpload(null);
        },
        onError: (error) => toast({ title: "Não foi possível enviar", description: errorMessage(error), variant: "error" }),
      },
    );
    for (const extra of rest) {
      uploadMore.mutate(
        { file: extra, analysisId: target },
        {
          onError: (error) =>
            toast({ title: `Não foi possível enviar “${extra.name}”`, description: errorMessage(error), variant: "error" }),
        },
      );
    }
  };

  const openDocument = (target: DocumentInfo) => {
    if (target.id === documentId) return;
    setPendingUpload(null);
    setDocumentId(target.id);
    setAnalysisId(target.analysis_id);
    resetView();
  };

  const ensureAnalysis = async () => {
    if (analysisId) return analysisId;
    const created = await createAnalysis.mutateAsync(undefined);
    setAnalysisId(created.id);
    return created.id;
  };

  const closeDocument = () => {
    setPendingUpload(null);
    setDocumentId(null);
    setAnalysisId(null);
    resetView();
  };

  const note = (content: string) =>
    setNotes((list) => [...list, { id: localId(), role: "assistant", content }]);

  const send = async () => {
    const text = draft.trim();
    if (!text || sending) return;
    if (!documentId || !doc) {
      setDraft("");
      setNotes((list) => [...list, { id: localId(), role: "user", content: text }]);
      note("Envie um contrato, edital ou regulamento (PDF, HTML, texto ou link) e eu respondo com base nele.");
      return;
    }
    if (!ready) {
      note("Ainda estou lendo o documento. Assim que terminar, respondo sua pergunta.");
      return;
    }
    setDraft("");
    setSending(true);
    const answerId = localId();
    setPending([
      { id: localId(), role: "user", content: text },
      { id: answerId, role: "assistant", content: "", streaming: true },
    ]);
    let answer = "";
    try {
      await streamMessage(documentId, text, {
        onDelta: (delta) => {
          answer += delta;
          setPending((list) =>
            list.map((m) => (m.id === answerId ? { ...m, content: stripCitations(answer) } : m)),
          );
        },
        onDone: () => undefined,
      });
      await invalidateMessages(queryClient, documentId);
    } catch (error) {
      toast({ title: "A IA não respondeu", description: errorMessage(error), variant: "error" });
      await invalidateMessages(queryClient, documentId);
    } finally {
      setPending([]);
      setSending(false);
    }
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
      pageEl.getBoundingClientRect().top -
      scroller.getBoundingClientRect().top +
      scroller.scrollTop +
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
    const box = rule.boxes[0];
    // Na troca de aba, espera a página aparecer antes de rolar.
    if (box) requestAnimationFrame(() => scrollToPage(box.page, box));
  };

  const goToMatch = (index: number) => {
    const total = search.matches.length;
    if (!total) return;
    const next = ((index % total) + total) % total;
    setSearchIndex(next);
    if (!isDesktop) setMobileTab("document");
    const match = search.matches[next];
    requestAnimationFrame(() => scrollToPage(match.page, match.rect));
  };

  const onPageMouseUp = (pageNumber: number, pageEl: HTMLElement) => {
    if (!ready) return;
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !pageEl.contains(sel.anchorNode)) return;
    const text = sel.toString().replace(/\s+/g, " ").trim();
    if (text.length < 2) return;
    selectionRef.current = sel.getRangeAt(0);
    selectionInfo.current = { page: pageNumber, text };
    setCreateOpen(true);
  };

  const onPageClick = (pageNumber: number, point: { x: number; y: number }) => {
    const hit = rules.find((r) =>
      r.boxes.some(
        (b) =>
          b.page === pageNumber &&
          point.x >= b.x &&
          point.x <= b.x + b.width &&
          point.y >= b.y &&
          point.y <= b.y + b.height,
      ),
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
      accept={DOCUMENT_ACCEPT}
      multiple
      className="sr-only"
      tabIndex={-1}
      aria-hidden
      onChange={(e) => {
        void openFiles(Array.from(e.target.files ?? []));
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
      void openFiles(Array.from(e.dataTransfer.files));
    },
  };

  const composer = (
    <AssistantComposer
      value={draft}
      onChange={setDraft}
      onSubmit={send}
      onAttach={attach}
      documentName={documentName || null}
      // Com documento aberto, o nome dele já aparece no topo da conversa.
      showDocument={!isOpen}
    />
  );

  // ----- Sem documento: conversa centralizada, no estilo do lineFlow -----
  const sourceDialog = (
    <DocumentSourceDialog
      mode={sourceMode}
      onModeChange={setSourceMode}
      ensureAnalysis={ensureAnalysis}
      onCreated={openDocument}
    />
  );

  if (!isOpen) {
    const recentDocs = (recent ?? []).slice(0, 4);
    return (
      <div className="relative flex h-full flex-col" {...dropHandlers}>
        {fileInput}
        <Glow />
        <div className="relative flex items-center gap-2 px-6 pt-6">
          <span className="text-base font-semibold">Grifo IA</span>
          <span className="rounded-full border border-accent/40 px-2 py-0.5 text-[11px] font-medium text-accent">Beta</span>
        </div>

        {notes.length === 0 ? (
          <div className="relative flex min-h-0 flex-1 flex-col items-center overflow-auto px-4 py-6 text-center">
            <div className="my-auto flex w-full max-w-xl flex-col items-center gap-4">
              <h1 className="text-[28px] leading-tight font-medium tracking-tight sm:text-[38px]">
                Pronto para validar, {user ? firstName(user.name) : ""}?
              </h1>
              <p className="max-w-md text-sm text-foreground-muted">
                Envie as bases de dados que serão verificadas e depois o documento. A IA encontra as regras, grifa cada
                uma e busca nas bases os registros ligados a ela.
              </p>

              <section aria-labelledby="step-datasets" className="mt-2 flex w-full flex-col gap-2 text-left">
                <h2 id="step-datasets" className="text-[13px] font-medium">
                  <span className="text-foreground-subtle">1.</span> Bases de dados (CSV)
                </h2>
                <DatasetUploader datasets={analysis?.datasets ?? []} ensureAnalysis={ensureAnalysis} />
              </section>

              <section aria-labelledby="step-document" className="flex w-full flex-col gap-2 text-left">
                <h2 id="step-document" className="text-[13px] font-medium">
                  <span className="text-foreground-subtle">2.</span> Documento
                </h2>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant="primary"
                    icon={<FileUp size={16} strokeWidth={1.75} aria-hidden />}
                    onClick={attach}
                    className="rounded-full"
                  >
                    Enviar arquivos
                  </Button>
                  <Button
                    size="sm"
                    icon={<Type size={16} strokeWidth={1.75} aria-hidden />}
                    onClick={() => setSourceMode("text")}
                    className="rounded-full"
                  >
                    Colar texto
                  </Button>
                  <Button
                    size="sm"
                    icon={<Link2 size={16} strokeWidth={1.75} aria-hidden />}
                    onClick={() => setSourceMode("url")}
                    className="rounded-full"
                  >
                    Usar um link
                  </Button>
                  <Link
                    href="/regras"
                    className="inline-flex h-8 items-center gap-2 rounded-full border border-border-strong bg-surface px-3 text-[13px] font-medium transition-colors duration-150 ease-out hover:bg-surface-hover"
                  >
                    <Library size={16} strokeWidth={1.75} aria-hidden />
                    Ver base de regras
                  </Link>
                </div>
                <p className="text-xs text-foreground-subtle">
                  PDF, HTML ou TXT, vários de uma vez. PDFs digitalizados (só imagem) precisam passar por OCR antes.
                </p>
                {!analysis?.datasets.length && (
                  <p className="text-xs text-foreground-subtle">
                    Sem bases, a IA só encontra as regras do documento, sem buscar registros.
                  </p>
                )}
              </section>

              {recentDocs.length > 0 && (
                <div className="mt-4 flex w-full flex-col gap-2">
                  <span className="text-xs text-foreground-subtle">Documentos recentes</span>
                  <ul className="flex flex-wrap justify-center gap-2">
                    {recentDocs.map((d) => (
                      <li key={d.id}>
                        <Button
                          size="sm"
                          variant="secondary"
                          icon={<FileText size={16} strokeWidth={1.75} aria-hidden />}
                          onClick={() => openDocument(d)}
                          className="max-w-64 rounded-full"
                        >
                          <span className="truncate">{d.title}</span>
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        ) : (
          <ChatThread messages={notes} className="relative mx-auto w-full max-w-3xl flex-1 px-4 py-6" />
        )}

        <div className="relative mx-auto w-full max-w-3xl px-4 pb-4">
          {composer}
          <AssistantDisclaimer className="mt-2" />
        </div>
        {sourceDialog}
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

  // Etapa atual: 0 enviando, 1 lendo, 2 identificando regras, 3 pronto.
  const step = upload.isPending ? 0 : !doc || doc.status === "processing" ? 1 : doc.status === "extracting_rules" ? 2 : 3;
  const failed = upload.isError || doc?.status === "error";
  const failedStep = upload.isError ? 0 : doc?.page_count ? 2 : 1;

  // Regerando as buscas: as regras continuam na tela, com um aviso.
  const generating = doc?.status === "extracting_rules" && rules.length > 0;
  const showRules = ready || generating;

  const intro: ThreadMessage = {
    id: "intro",
    role: "assistant",
    content: failed
      ? `Não consegui analisar “${documentName}”. ${doc?.status_message ?? errorMessage(upload.error)}`
      : showRules
        ? `Li “${documentName}” e encontrei ${rules.length} ${rules.length === 1 ? "regra" : "regras"}. Revise na tabela ao lado ou me pergunte sobre o documento.`
        : `Estou lendo “${documentName}” e procurando as regras. ${doc?.status_message ?? ""}`,
  };
  const thread: ThreadMessage[] = [
    intro,
    ...savedMessages.map((m) => ({ id: m.id, role: m.role, content: m.content, citations: m.citations })),
    ...notes,
    ...pending,
  ];

  const analysisDocuments = analysis?.documents ?? [];

  const chatPanel = (
    <section aria-label="Conversa" className="flex h-full min-h-0 flex-col bg-background">
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-3">
        <FileText size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-accent" />
        {documentId && analysisDocuments.length > 1 ? (
          <Select
            aria-label="Documento da análise"
            value={documentId}
            onChange={(e) => {
              const target = analysisDocuments.find((d) => d.id === e.target.value);
              if (target) openDocument(target);
            }}
            className="min-w-0 flex-1 [&_select]:h-8 [&_select]:text-[13px]"
          >
            {analysisDocuments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title}
              </option>
            ))}
          </Select>
        ) : (
          <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{documentName}</span>
        )}
        {pdf.status === "ready" && (
          <span className="shrink-0 font-mono text-xs text-foreground-subtle tabular-nums">{pdf.pages.length} p.</span>
        )}
        <IconButton
          aria-label="Adicionar arquivos à análise"
          icon={<FilePlus size={16} strokeWidth={1.75} aria-hidden />}
          onClick={attach}
          tooltipSide="bottom"
        />
        <IconButton
          aria-label="Adicionar texto ou link à análise"
          icon={<Link2 size={16} strokeWidth={1.75} aria-hidden />}
          onClick={() => setSourceMode("url")}
          tooltipSide="bottom"
        />
        {isDesktop && (
          <IconButton
            aria-label="Esconder conversa"
            icon={<PanelLeftClose size={16} strokeWidth={1.75} aria-hidden />}
            onClick={() => setLayout({ ...layout, chat: false })}
            tooltipSide="bottom"
          />
        )}
        <IconButton aria-label="Fechar análise" icon={<X size={16} strokeWidth={1.75} aria-hidden />} onClick={closeDocument} />
      </div>
      <ChatThread
        messages={thread}
        className="flex-1 px-4 py-5"
        onCitationHighlight={setHoverId}
        onCitationClick={goToRule}
      />
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
            actions={
              <>
                <IconButton
                  aria-label="Buscar no documento (Ctrl+F)"
                  icon={<Search size={16} strokeWidth={1.75} aria-hidden />}
                  onClick={() => setSearchOpen(true)}
                  disabled={pdf.status !== "ready"}
                  tooltipSide="bottom"
                />
                {isDesktop && (
                  <PanelToggles
                    layout={layout}
                    onChange={setLayout}
                    counts={{ rules: rules.length, table: rules.filter((r) => r.query?.state === "ok").length }}
                  />
                )}
              </>
            }
          />
          <RuleLegend active={typeFilter} onChange={setTypeFilter} />
        </>
      }
      overlay={
        searchOpen && (
          <SearchBar
            query={searchQuery}
            onQueryChange={(q) => {
              setSearchQuery(q);
              setSearchIndex(0);
            }}
            current={search.matches.length ? Math.min(searchIndex, search.matches.length - 1) : 0}
            total={search.matches.length}
            onPrevious={() => goToMatch(searchIndex - 1)}
            onNext={() => goToMatch(searchIndex + 1)}
            onClose={() => setSearchOpen(false)}
            className="absolute top-3 right-3 z-20"
          />
        )
      }
    >
      {documentFile.isError ? (
        <EmptyState
          icon={FileText}
          title="Não foi possível baixar o documento"
          description={errorMessage(documentFile.error)}
          action={
            <Button size="sm" onClick={() => void documentFile.refetch()}>
              Tentar de novo
            </Button>
          }
          className="mt-16"
        />
      ) : pdf.status === "error" ? (
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
                .filter((r) => r.boxes.some((b) => b.page === n))
                .map((r) => ({ ruleId: r.id, type: r.type, status: r.status, rects: rectsOn(r, n) }))}
              activeRuleId={activeRuleId}
              pulse={pulse}
              searchRects={search.matches.filter((m) => m.page === n).map((m) => m.rect)}
              currentSearchIndex={
                search.matches[searchIndex]?.page === n
                  ? search.matches.slice(0, searchIndex).filter((m) => m.page === n).length
                  : undefined
              }
            />
          )}
        />
      ) : (
        // Proporção de uma folha A4 enquanto o PDF abre.
        [1, 2].map((n) => (
          <PdfPage key={n} pageNumber={n} width={595 * zoom * PDF_TO_CSS} height={842 * zoom * PDF_TO_CSS} loading />
        ))
      )}
    </PdfViewer>
  );

  const rulesPanel = (
    <section aria-label="Regras" className="flex h-full min-h-0 flex-col bg-surface">
      {showRules ? (
        <>
          <RulesHeader
            validated={rules.filter((r) => r.status === "validada").length}
            total={rules.length}
            typeFilter={typeFilter}
            onTypeFilterChange={setTypeFilter}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
            notice={generating ? "Gerando as buscas nas bases de dados…" : doc?.status_message}
            actions={
              <>
                {datasets.length > 0 && rules.length > 0 && (
                  <Button
                    size="sm"
                    icon={<Sparkles size={16} strokeWidth={1.75} aria-hidden />}
                    loading={generateQueries.isPending || generating}
                    onClick={() =>
                      generateQueries.mutate(false, {
                        onError: (error) =>
                          toast({ title: "Não foi possível gerar as buscas", description: errorMessage(error), variant: "error" }),
                      })
                    }
                  >
                    Gerar buscas com IA
                  </Button>
                )}
                {isDesktop && (
                  <IconButton
                    aria-label="Esconder regras"
                    icon={<X size={16} strokeWidth={1.75} aria-hidden />}
                    onClick={() => setLayout({ ...layout, rules: false })}
                  />
                )}
              </>
            }
          />
          <RulesTable
            className="flex-1"
            rules={visibleRules.map((r) => ({
              ...r,
              page: r.page ?? undefined,
              query: r.query ? { ...r.query, description: describeQuery(r.query.query) } : null,
            }))}
            onEditQuery={datasets.length ? (r) => setEditingQueryId(r.id) : undefined}
            selectedId={selectedId}
            onSelect={(r) => goToRule(r.id)}
            onHover={(r) => setHoverId(r?.id ?? null)}
            onSetStatus={(rule, status) =>
              updateRule.mutate(
                { id: rule.id, status },
                {
                  onError: (error) =>
                    toast({ title: "Não foi possível salvar", description: errorMessage(error), variant: "error" }),
                },
              )
            }
            empty={
              rules.length === 0 ? (
                <EmptyState
                  icon={MousePointerClick}
                  title="Nenhuma regra encontrada"
                  description="Selecione um trecho do documento e clique em “Criar regra”."
                />
              ) : undefined
            }
          />
        </>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 p-6" aria-live="polite">
          <FileSearch size={32} strokeWidth={1.5} aria-hidden className={failed ? "text-danger" : "text-accent"} />
          <ProcessingSteps current={failed ? failedStep : step} failed={failed} />
          <p className={cn("max-w-72 text-center text-[13px]", failed ? "text-danger" : "text-foreground-muted")}>
            {failed
              ? (doc?.status_message ?? errorMessage(upload.error))
              : (doc?.status_message ?? "Isso leva de alguns segundos a poucos minutos, conforme o tamanho do documento.")}
          </p>
          {failed && (
            <Button size="sm" variant="primary" onClick={attach}>
              Enviar de novo
            </Button>
          )}
        </div>
      )}
    </section>
  );

  const tablePanel = (onClose?: () => void) => (
    <RecordsPanel
      rules={rules}
      selectedRuleId={selectedId}
      onSelectRule={(id) => (id ? goToRule(id) : setSelectedId(null))}
      hasDatasets={datasets.length > 0}
      onEditQuery={(rule) => setEditingQueryId(rule.id)}
      onClose={onClose}
    />
  );

  return (
    <div className="relative h-full" {...dropHandlers}>
      {fileInput}
      {isDesktop ? (
        <AnalysisWorkspace
          layout={layout}
          chat={chatPanel}
          document={documentPanel}
          rules={rulesPanel}
          table={tablePanel(() => setLayout({ ...layout, table: false }))}
        />
      ) : (
        <div className="flex h-full flex-col">
          <MobileTabs value={mobileTab} onChange={setMobileTab} ruleCount={rules.length} />
          <div className="min-h-0 flex-1">
            {mobileTab === "chat"
              ? chatPanel
              : mobileTab === "document"
                ? documentPanel
                : mobileTab === "rules"
                  ? rulesPanel
                  : tablePanel()}
          </div>
        </div>
      )}

      {sourceDialog}
      <QueryEditorDialog
        rule={rules.find((r) => r.id === editingQueryId) ?? null}
        datasets={datasets}
        documentId={documentId ?? ""}
        onClose={() => setEditingQueryId(null)}
      />
      <CreateRulePopover
        open={createOpen}
        onOpenChange={setCreateOpen}
        anchorRef={selectionRef}
        creating={createRule.isPending}
        onCreate={({ type, summary }) => {
          const info = selectionInfo.current;
          if (!info) return;
          createRule.mutate(
            { type, summary, page: info.page, excerpt: info.text },
            {
              onSuccess: (rule) => {
                setCreateOpen(false);
                setSelectedId(rule.id);
                window.getSelection()?.removeAllRanges();
                toast({ title: "Regra criada", variant: "success" });
              },
              onError: (error) =>
                toast({ title: "Não foi possível criar a regra", description: errorMessage(error), variant: "error" }),
            },
          );
        }}
      />
      {dragging && <DropOverlay />}
    </div>
  );
}

function ChatThread({
  messages,
  className,
  onCitationHighlight,
  onCitationClick,
}: {
  messages: ThreadMessage[];
  className?: string;
  onCitationHighlight?: (ruleId: string | null) => void;
  onCitationClick?: (ruleId: string) => void;
}) {
  return (
    <div role="log" aria-label="Mensagens" className={cn("flex min-h-0 flex-col gap-5 overflow-auto", className)}>
      {messages.map((m) =>
        m.role === "user" ? (
          <UserMessage key={m.id}>{m.content}</UserMessage>
        ) : (
          <AssistantMessage
            key={m.id}
            streaming={m.streaming}
            citations={m.citations}
            onCitationHighlight={onCitationHighlight}
            onCitationClick={onCitationClick}
          >
            {m.content}
          </AssistantMessage>
        ),
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
      <p className="text-sm font-medium">Solte os arquivos para analisar</p>
      <p className="text-xs text-foreground-muted">PDF, HTML ou TXT</p>
    </div>
  );
}

const TABS: { value: MobileTab; label: string }[] = [
  { value: "chat", label: "Conversa" },
  { value: "document", label: "Documento" },
  { value: "rules", label: "Regras" },
  { value: "table", label: "Tabela" },
];

function MobileTabs({
  value,
  onChange,
  ruleCount,
}: {
  value: MobileTab;
  onChange: (tab: MobileTab) => void;
  ruleCount: number;
}) {
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
          {value === tab.value && (
            <span aria-hidden className="bg-brand-gradient absolute inset-x-3 bottom-0 h-0.5 rounded-full" />
          )}
        </button>
      ))}
    </div>
  );
}
