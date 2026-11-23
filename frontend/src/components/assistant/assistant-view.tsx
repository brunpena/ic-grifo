"use client";

import {
  Database,
  FileSearch,
  FileText,
  FileUp,
  History,
  Link2,
  MousePointerClick,
  Search,
  Sparkles,
  Type,
  X,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { type DragEvent, useEffect, useRef, useState } from "react";
import { type AnalysisLayout, PanelToggles } from "@/components/analysis/panel-toggles";
import { BrandLogo } from "@/components/brand-logo";
import { ProcessingSteps } from "@/components/chat/processing-steps";
import { DatasetUploader } from "@/components/datasets/dataset-uploader";
import { DocumentSourceDialog, type DocumentSourceMode } from "@/components/documents/document-source-dialog";
import { AnalysisHistory } from "@/components/history/analysis-history";
import { HighlightLayer, type PageRect } from "@/components/document/highlight-layer";
import { PDF_TO_CSS, PdfDocumentPages, usePdfDocument } from "@/components/document/pdf-document";
import { PdfPage, PdfViewer } from "@/components/document/pdf-viewer";
import { PdfToolbar } from "@/components/document/pdf-toolbar";
import { RecordsTableSkeleton, RulesOverviewSkeleton } from "@/components/records/records-skeleton";
import { RuleLegend } from "@/components/document/rule-legend";
import { SearchBar } from "@/components/document/search-bar";
import { usePdfSearch } from "@/components/document/use-pdf-search";
import { RulesHeader } from "@/components/rules/rules-header";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { IconButton } from "@/components/ui/icon-button";
import { useToast } from "@/components/ui/toast";
import { closeAnalysis, useAnalysis, useCloseAnalysis, useCreateAnalysis } from "@/lib/analyses";
import { errorMessage } from "@/lib/api";
import { firstName, useCurrentUser } from "@/lib/auth";
import { msg, useT } from "@/lib/i18n";
import { useAnalysisLifecycle, useAssistantRoute } from "./assistant-route";
import type { RuleStatus, RuleType } from "@/lib/design/tokens";
import {
  DOCUMENT_ACCEPT,
  type DocumentInfo,
  isDocumentFile,
  isPdfFile,
  type Rule,
  useCreateRule,
  useDocument,
  useDocumentFile,
  useRules,
  useResumeDocument,
  seedDocument,
  useUpdateRule,
  useUploadDocument,
} from "@/lib/documents";
import type { FloatingAnchor } from "@/lib/floating";
import { describeQuery, useGenerateQueries } from "@/lib/queries";
import { DESKTOP_QUERY, useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";

// Peças do espaço de trabalho (documento aberto) ficam fora do pacote inicial: a tela de
// entrada só mostra o envio das bases e o histórico. `preloadWorkspace` baixa esses
// pacotes assim que uma análise começa, antes de o documento ficar pronto.
const loadWorkspace = () => import("@/components/analysis/analysis-workspace");
const loadRulesTable = () => import("@/components/rules/rules-table");
const loadRecordsPanel = () => import("@/components/records/records-panel");
const loadQueryEditor = () => import("@/components/queries/query-editor-dialog");
const loadCreateRule = () => import("@/components/document/create-rule-popover");

function preloadWorkspace() {
  void Promise.all([loadWorkspace(), loadRulesTable(), loadRecordsPanel(), loadQueryEditor(), loadCreateRule()]).catch(() => {
    // Sem rede agora: cada parte tenta de novo quando for exibida.
  });
}

const AnalysisWorkspace = dynamic(() => loadWorkspace().then((m) => m.AnalysisWorkspace), {
  loading: () => <Skeleton className="m-4 h-[calc(100%-2rem)]" />,
});
const RulesTable = dynamic(() => loadRulesTable().then((m) => m.RulesTable), {
  loading: () => <RulesOverviewSkeleton />,
});
const RecordsPanel = dynamic(() => loadRecordsPanel().then((m) => m.RecordsPanel), {
  loading: () => <RecordsTableSkeleton columns={null} />,
});
const QueryEditorDialog = dynamic(() => loadQueryEditor().then((m) => m.QueryEditorDialog));
const CreateRulePopover = dynamic(() => loadCreateRule().then((m) => m.CreateRulePopover));

type MobileTab = "document" | "rules" | "table";

const EMPTY_RULES: Rule[] = [];

const rectsOn = (rule: Rule, page: number): PageRect[] =>
  rule.boxes.filter((b) => b.page === page).map(({ x, y, width, height }) => ({ x, y, width, height }));

export function AssistantView() {
  const toast = useToast();
  const t = useT();
  const queryClient = useQueryClient();
  const { data: user } = useCurrentUser();
  const isDesktop = useMediaQuery(DESKTOP_QUERY);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [viewerWidth, setViewerWidth] = useState(0);

  // Análise e documento vêm da URL (ver o layout de /assistente); `navigate` troca a URL.
  const route = useAssistantRoute();
  const { documentId } = route;
  const docQuery = useDocument(documentId);
  const { data: doc } = docQuery;
  // Na página do documento, a análise vem do próprio documento.
  const analysisId = route.analysisId ?? doc?.analysis_id ?? null;
  const analysisQuery = useAnalysis(analysisId);
  const { data: analysis } = analysisQuery;

  // Primeiro envio ainda sem resposta: o nome e, se for PDF, o arquivo para já exibir. Só
  // aparece na análise para a qual foi enviado (Voltar/Avançar levam a outras telas).
  const [pendingUpload, setPendingUpload] = useState<{ name: string; file: File | null; analysisId: string } | null>(null);
  const showPending = !documentId && !!pendingUpload && pendingUpload.analysisId === analysisId;
  const [datasetsOpen, setDatasetsOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [sourceMode, setSourceMode] = useState<DocumentSourceMode | null>(null);
  const createAnalysis = useCreateAnalysis();
  const creatingAnalysis = useRef<Promise<string> | null>(null);
  const endAnalysis = useCloseAnalysis();
  const [dragging, setDragging] = useState(false);
  const upload = useUploadDocument();
  // O estado do envio só vale enquanto a tela mostra esse envio.
  const shownUpload = showPending ? upload : null;
  const resumeDocument = useResumeDocument();
  const uploadMore = useUploadDocument();
  // Texto, HTML e links viram PDF no back; o PDF exibido vem sempre de lá (ou do cache).
  const documentFile = useDocumentFile(doc);
  const file = documentId ? (documentFile.data ?? null) : showPending ? pendingUpload.file : null;
  const documentName = doc?.title ?? (showPending ? pendingUpload.name : "");
  const isOpen = !!documentId || showPending;
  const pdf = usePdfDocument(file);
  const [layout, setLayout] = useState<AnalysisLayout>({ chat: false, rules: true, table: true });
  // Busca no documento (Ctrl+F).
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchIndex, setSearchIndex] = useState(0);
  const search = usePdfSearch(pdf.status === "ready" ? pdf.doc : null, searchOpen ? searchQuery : "");
  const ready = doc?.status === "ready";
  const rulesQuery = useRules(documentId, ready);
  const rules = rulesQuery.data ?? EMPTY_RULES;
  const updateRule = useUpdateRule(documentId ?? "");
  const createRule = useCreateRule(documentId ?? "");
  const generateQueries = useGenerateQueries(documentId ?? "");
  const [editingQueryId, setEditingQueryId] = useState<string | null>(null);
  // Só as bases já lidas no servidor entram nas buscas das regras.
  const datasets = (analysis?.datasets ?? []).filter((d) => d.status === "ready");
  const canUploadDocument = (analysis?.datasets ?? []).some(
    (d) => d.status !== "error" && d.columns.length > 0,
  );

  // Uma análise começou (base enviada ou histórico reaberto): o espaço de trabalho vem a seguir.
  useEffect(() => {
    if (analysisId) preloadWorkspace();
  }, [analysisId]);

  // Encerra a análise ao trocar por outra, sair do Assistente ou fechar a aba.
  const closedAnalyses = useAnalysisLifecycle(analysisId);
  // Ids da tela atual, para callbacks que terminam depois (ex.: fim de um envio).
  const currentIds = useRef({ analysisId, documentId });
  useEffect(() => {
    currentIds.current = { analysisId, documentId };
  });

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

  // Outro documento (ou nenhum) na URL: a visualização volta ao padrão. Ajuste durante a
  // renderização, sem efeito: a tela nova já aparece com o estado certo.
  const [viewFor, setViewFor] = useState(documentId);
  if (viewFor !== documentId) {
    setViewFor(documentId);
    setDatasetsOpen(false);
    setZoomOverride(null);
    setSelectedId(null);
    setPage(1);
    setMobileTab("rules");
    setLayout({ chat: false, rules: true, table: true });
    setSearchIndex(0);
  }

  /** Envia os arquivos para a análise atual e abre o primeiro. */
  const openFiles = async (picked: File[]) => {
    if (!canUploadDocument) {
      toast({ title: t("Envie a base de dados primeiro"), description: t("Aguarde a leitura da base antes de enviar o documento."), variant: "error" });
      return;
    }
    const invalid = picked.filter((f) => !isDocumentFile(f));
    if (invalid.length) {
      toast({
        title: t("Formato não suportado"),
        description: t("{files}: envie PDF, HTML ou TXT.", { files: invalid.map((f) => `“${f.name}”`).join(", ") }),
        variant: "error",
      });
    }
    const [first, ...rest] = picked.filter(isDocumentFile);
    if (!first) return;
    let target: string;
    try {
      target = await ensureAnalysis();
    } catch (error) {
      toast({ title: t("Não foi possível criar a análise"), description: errorMessage(error, t), variant: "error" });
      return;
    }
    setPendingUpload({ name: first.name, file: isPdfFile(first) ? first : null, analysisId: target });
    // Enviar outro documento a partir de um já aberto: volta para a tela da análise.
    if (documentId) route.navigate({ analysisId: target, documentId: null });
    upload.mutate(
      { file: first, analysisId: target },
      {
        onSuccess: (created) => {
          // Um upload pode terminar depois que a pessoa encerrou o uso.
          if (closedAnalyses.current.has(target)) {
            void closeAnalysis(target, true).catch(() => {});
            return;
          }
          // Só abre o documento se a pessoa continua na análise para a qual ele foi enviado.
          if (currentIds.current.analysisId === target) route.navigate({ analysisId: target, documentId: created.id });
        },
        onError: (error) => toast({ title: t("Não foi possível enviar"), description: errorMessage(error, t), variant: "error" }),
      },
    );
    for (const extra of rest) {
      uploadMore.mutate(
        { file: extra, analysisId: target },
        {
          onSuccess: () => {
            if (closedAnalyses.current.has(target)) {
              void closeAnalysis(target, true).catch(() => {});
            }
          },
          onError: (error) =>
            toast({ title: t("Não foi possível enviar “{name}”", { name: extra.name }), description: errorMessage(error, t), variant: "error" }),
        },
      );
    }
  };

  const openDocument = (target: DocumentInfo) => {
    setHistoryOpen(false);
    if (target.id === documentId) return;
    // O histórico já trouxe o documento: PDF e regras começam a carregar sem esperar
    // outra consulta; a situação atual é conferida em segundo plano.
    seedDocument(queryClient, target);
    route.navigate({ analysisId: target.analysis_id, documentId: target.id });
  };

  /** Análise atual; cria uma (e vai para o endereço dela) na primeira base enviada. */
  const ensureAnalysis = async () => {
    if (analysisId) return analysisId;
    // Vários arquivos soltos de uma vez: todos esperam a mesma criação.
    creatingAnalysis.current ??= createAnalysis
      .mutateAsync(undefined)
      .then((created) => {
        route.navigate({ analysisId: created.id, documentId: null });
        return created.id;
      })
      .finally(() => {
        creatingAnalysis.current = null;
      });
    return creatingAnalysis.current;
  };

  const closeDocument = async () => {
    if (endAnalysis.isPending) return;
    if (analysisId) {
      closedAnalyses.current.add(analysisId);
      try {
        await endAnalysis.mutateAsync(analysisId);
      } catch (error) {
        closedAnalyses.current.delete(analysisId);
        toast({ title: t("Não foi possível encerrar a análise"), description: errorMessage(error, t), variant: "error" });
        return;
      }
    }
    setPendingUpload(null);
    upload.reset();
    route.navigate({ analysisId: null, documentId: null });
  };

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

  const sourceDialog = (
    <DocumentSourceDialog
      mode={sourceMode}
      onModeChange={setSourceMode}
      ensureAnalysis={ensureAnalysis}
      onCreated={openDocument}
    />
  );

  // Endereço de uma análise ou documento que não existe (ou de outra conta).
  const routeError = (documentId && docQuery.isError && !doc ? docQuery.error : null)
    ?? (route.analysisId && analysisQuery.isError && !analysis ? analysisQuery.error : null);
  if (routeError) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <EmptyState
          icon={FileSearch}
          title={documentId ? t("Não foi possível abrir o documento") : t("Não foi possível abrir a análise")}
          description={errorMessage(routeError, t)}
          action={
            <Button size="sm" variant="primary" onClick={() => route.navigate({ analysisId: null, documentId: null }, { replace: true })}>
              {t("Nova análise")}
            </Button>
          }
        />
      </div>
    );
  }

  if (!isOpen) {
    return (
      <div className="relative flex h-full flex-col" {...dropHandlers}>
        {fileInput}<Glow />
        <div className="relative flex min-h-0 flex-1 flex-col items-center overflow-auto px-4 py-8">
          <div className="my-auto flex w-full max-w-2xl flex-col gap-6">
            <WorkflowSteps current={canUploadDocument ? 2 : 1} />
            <div className="text-center">
              <h1 className="text-3xl font-medium tracking-tight">
                {user ? t("Vamos validar seus dados, {name}?", { name: firstName(user.name) }) : t("Vamos validar seus dados?")}
              </h1>
              <p className="mt-3 text-sm text-foreground-muted">{t("Envie a base de dados, adicione o documento de regras e confira o resultado em tabelas.")}</p>
            </div>
            <section aria-labelledby="step-datasets" className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-5">
              <h2 id="step-datasets" className="font-medium">{t("1. Envie a base de dados")}</h2>
              <DatasetUploader datasets={analysis?.datasets ?? []} ensureAnalysis={ensureAnalysis} />
            </section>
            {canUploadDocument ? (
              <section aria-labelledby="step-document" className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-5">
                <h2 id="step-document" className="font-medium">{t("2. Envie o documento com as regras")}</h2>
                <p className="text-sm text-foreground-muted">{t("A IA identifica as regras e prepara consultas usando o significado das colunas. Selecione uma regra para ver os registros.")}</p>
                <div className="flex flex-wrap gap-2">
                  <Button variant="primary" icon={<FileUp size={16} aria-hidden />} onClick={attach}>{t("Enviar documento")}</Button>
                  <Button icon={<Type size={16} aria-hidden />} onClick={() => setSourceMode("text")}>{t("Colar texto")}</Button>
                  <Button icon={<Link2 size={16} aria-hidden />} onClick={() => setSourceMode("url")}>{t("Usar um link")}</Button>
                </div>
                <p className="text-xs text-foreground-subtle">{t("PDF, HTML ou TXT.")}</p>
              </section>
            ) : <p role="status" className="text-center text-sm text-foreground-muted">{t("O envio do documento fica disponível após a leitura da base de dados.")}</p>}
            {!analysisId && (
              <section aria-labelledby="history" className="flex flex-col gap-3 rounded-xl border border-border bg-surface p-5">
                <h2 id="history" className="flex items-center gap-2 font-medium">
                  <History size={16} aria-hidden /> {t("Histórico de análises")}
                </h2>
                <p className="text-sm text-foreground-muted">{t("Reabra uma análise anterior com as regras, as consultas e a tabela já prontas.")}</p>
                <AnalysisHistory onOpen={openDocument} className="max-h-80 overflow-y-auto" />
              </section>
            )}
          </div>
        </div>
        {sourceDialog}
        {dragging && canUploadDocument && <DropOverlay />}
      </div>
    );
  }

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
  const step = shownUpload?.isPending ? 0 : !doc || doc.status === "processing" ? 1 : doc.status === "extracting_rules" ? 2 : 3;
  const failed = !!shownUpload?.isError || doc?.status === "error";
  const failedStep = shownUpload?.isError ? 0 : doc?.page_count ? 2 : 1;

  // Regerando as buscas: as regras continuam na tela, com um aviso.
  const generating = doc?.status === "extracting_rules" && rules.length > 0;
  // Documento aberto pelo endereço ou pelo histórico: a situação ainda não chegou, mostra o
  // espaço de trabalho em skeleton.
  const opening = !!documentId && !doc;
  const showRules = ready || generating || opening;
  const rulesLoading = opening || (ready && rulesQuery.isPending);

  const resumeAction = doc?.status === "error" ? (
              <Button size="sm" variant="primary" disabled={resumeDocument.isPending}
                onClick={() => {
                  if (!doc) return;
                  resumeDocument.mutate(doc.id, {
                  onError: (error) => toast({ title: t("Não foi possível continuar"), description: errorMessage(error, t), variant: "error" }),
                  });
                }}>
                {resumeDocument.isPending ? t("Retomando...") : t("Continuar processamento")}
              </Button>
  ) : null;

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
                  aria-label={t("Buscar no documento (Ctrl+F)")}
                  icon={<Search size={16} strokeWidth={1.75} aria-hidden />}
                  onClick={() => setSearchOpen(true)}
                  disabled={pdf.status !== "ready"}
                  tooltipSide="bottom"
                />
                {isDesktop && (
                  <PanelToggles
                    layout={layout}
                    onChange={setLayout}
                    hiddenPanels={["chat"]}
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
      {doc?.status === "error" && pdf.status === "ready" && (
        <div role="alert" className="m-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-danger/40 bg-danger-soft p-4 text-sm">
          <p>{t(doc.status_message ?? "")} {t("Os pacotes concluídos foram preservados.")}</p>
          {resumeAction}
        </div>
      )}
      {documentFile.isError ? (
        <EmptyState
          icon={FileText}
          title={t("Não foi possível baixar o documento")}
          description={errorMessage(documentFile.error, t)}
          action={
            <Button size="sm" onClick={() => void documentFile.refetch()}>
              {t("Tentar de novo")}
            </Button>
          }
          className="mt-16"
        />
      ) : pdf.status === "error" ? (
        <EmptyState icon={FileText} title={t("Não foi possível abrir")} description={t(pdf.message)} className="mt-16" />
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
    <section aria-label={t("Regras")} className="flex h-full min-h-0 flex-col bg-surface">
      {showRules ? (
        <>
          <RulesHeader
            validated={rules.filter((r) => r.status === "validada").length}
            total={rules.length}
            typeFilter={typeFilter}
            onTypeFilterChange={setTypeFilter}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
            notice={generating ? t(doc?.status_message ?? msg("Verificando as regras nas bases…")) : doc?.status_message && t(doc.status_message)}
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
                          toast({ title: t("Não foi possível gerar as buscas"), description: errorMessage(error, t), variant: "error" }),
                      })
                    }
                  >
                    {t("Preparar consultas com IA")}
                  </Button>
                )}
                {isDesktop && (
                  <IconButton
                    aria-label={t("Esconder regras")}
                    icon={<X size={16} strokeWidth={1.75} aria-hidden />}
                    onClick={() => setLayout({ ...layout, rules: false })}
                  />
                )}
              </>
            }
          />
          <RulesTable
            className="flex-1"
            loading={rulesLoading}
            rules={visibleRules.map((r) => ({
              ...r,
              page: r.page ?? undefined,
              query: r.query ? { ...r.query, description: describeQuery(r.query.query, t) } : null,
            }))}
            onEditQuery={datasets.length ? (r) => setEditingQueryId(r.id) : undefined}
            selectedId={selectedId}
            onSelect={(r) => { goToRule(r.id); if (isDesktop) setLayout({ ...layout, table: true }); }}
            onHover={(r) => setHoverId(r?.id ?? null)}
            onSetStatus={(rule, status) =>
              updateRule.mutate(
                { id: rule.id, status },
                {
                  onError: (error) =>
                    toast({ title: t("Não foi possível salvar"), description: errorMessage(error, t), variant: "error" }),
                },
              )
            }
            empty={
              rules.length === 0 ? (
                <EmptyState
                  icon={MousePointerClick}
                  title={t("Nenhuma regra encontrada")}
                  description={t("Selecione um trecho do documento e clique em “Criar regra”.")}
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
              ? (doc?.status_message ? t(doc.status_message) : errorMessage(shownUpload?.error, t))
              : t(doc?.status_message ?? msg("Isso leva de alguns segundos a poucos minutos, conforme o tamanho do documento."))}
          </p>
          {failed && (
            doc?.status === "error" ? (
              resumeAction
            ) : (
              <Button size="sm" variant="primary" onClick={attach}>{t("Enviar de novo")}</Button>
            )
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
      hasDatasets={datasets.length > 0 || rulesLoading}
      rulesLoading={rulesLoading}
      onEditQuery={(rule) => setEditingQueryId(rule.id)}
      onClose={onClose}
    />
  );

  return (
    <div className="relative flex h-full flex-col" {...dropHandlers}>
      {fileInput}
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border bg-surface px-4 py-3">
        <div className="min-w-0 flex-1"><WorkflowSteps current={showRules ? 3 : 2} /><p className="mt-1 truncate text-xs text-foreground-muted">{documentName}</p></div>
        <Button size="sm" icon={<History size={16} aria-hidden />} onClick={() => setHistoryOpen(true)}>{t("Histórico")}</Button>
        <Button size="sm" icon={<Database size={16} aria-hidden />} onClick={() => setDatasetsOpen(true)}>{t("Bases de dados")}</Button>
        <Button size="sm" loading={endAnalysis.isPending} onClick={() => void closeDocument()}>{t("Nova análise")}</Button>
      </div>
      <div className="min-h-0 flex-1">
      {!showRules ? rulesPanel : isDesktop ? (
        <AnalysisWorkspace
          layout={layout}
          chat={null}
          document={documentPanel}
          rules={rulesPanel}
          table={tablePanel(() => setLayout({ ...layout, table: false }))}
        />
      ) : (
        <div className="flex h-full flex-col">
          <MobileTabs value={mobileTab} onChange={setMobileTab} ruleCount={rules.length} />
          <div className="min-h-0 flex-1">
            {mobileTab === "document"
                ? documentPanel
                : mobileTab === "rules"
                  ? rulesPanel
                  : tablePanel()}
          </div>
        </div>
      )}

      </div>
      {sourceDialog}
      <Dialog
        open={datasetsOpen}
        onOpenChange={setDatasetsOpen}
        title={t("Bases da análise")}
        description={t("Confira o significado das colunas usadas nas consultas das regras.")}
        className="max-h-[85dvh] w-[760px] overflow-y-auto"
      >
        <DatasetUploader datasets={analysis?.datasets ?? []} ensureAnalysis={ensureAnalysis} />
      </Dialog>
      <Dialog
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        title={t("Histórico de análises")}
        description={t("Seus documentos analisados, do mais recente ao mais antigo.")}
        className="max-h-[85dvh] w-[560px] overflow-y-auto"
      >
        {historyOpen && <AnalysisHistory currentDocumentId={documentId} onOpen={openDocument} />}
      </Dialog>
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
                toast({ title: t("Regra criada"), variant: "success" });
              },
              onError: (error) =>
                toast({ title: t("Não foi possível criar a regra"), description: errorMessage(error, t), variant: "error" }),
            },
          );
        }}
      />
      {dragging && <DropOverlay />}
    </div>
  );
}

const WORKFLOW_STEPS = [msg("Base de dados"), msg("Documento de regras"), msg("Resultado")];

function WorkflowSteps({ current }: { current: 1 | 2 | 3 }) {
  const t = useT();
  return (
    <ol aria-label={t("Etapas")} className="flex flex-wrap gap-x-5 gap-y-2 text-xs">
      {WORKFLOW_STEPS.map((label, index) => (
        <li key={label} aria-current={current === index + 1 ? "step" : undefined} className={cn("flex items-center gap-2", current === index + 1 ? "font-semibold text-accent" : "text-foreground-muted")}>
          <span className="flex size-6 items-center justify-center rounded-full border border-current">{index + 1}</span>{t(label)}
        </li>
      ))}
    </ol>
  );
}

function Glow() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_55%_50%_at_50%_45%,rgb(10_132_255/0.07),transparent_70%)] dark:bg-[radial-gradient(ellipse_55%_50%_at_50%_45%,rgb(10_132_255/0.15),transparent_70%)]"
    />
  );
}

function DropOverlay() {
  const t = useT();
  return (
    <div className="pointer-events-none absolute inset-3 z-30 flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-accent bg-accent-soft/80 backdrop-blur-sm">
      <BrandLogo size={40} />
      <p className="text-sm font-medium">{t("Solte os arquivos para analisar")}</p>
      <p className="text-xs text-foreground-muted">{t("PDF, HTML ou TXT")}</p>
    </div>
  );
}

const TABS: { value: MobileTab; label: string }[] = [
  { value: "document", label: msg("Documento") },
  { value: "rules", label: msg("Regras") },
  { value: "table", label: msg("Tabela") },
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
  const t = useT();
  return (
    <div role="tablist" aria-label={t("Painéis")} className="flex h-11 shrink-0 border-b border-border bg-surface px-2">
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
          {t(tab.label)}
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
