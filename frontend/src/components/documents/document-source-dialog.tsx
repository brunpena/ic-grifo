"use client";

import { Link2, Type } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, FormError, fieldDescribedBy } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { errorMessage } from "@/lib/api";
import { type DocumentInfo, useCreateTextDocument, useCreateUrlDocument } from "@/lib/documents";
import { cn } from "@/lib/utils";

export type DocumentSourceMode = "text" | "url";

type DocumentSourceDialogProps = {
  /** `null` fecha o diálogo. */
  mode: DocumentSourceMode | null;
  onModeChange: (mode: DocumentSourceMode | null) => void;
  /** Devolve a análise onde criar o documento (pode criá-la na hora). */
  ensureAnalysis: () => Promise<string>;
  onCreated: (doc: DocumentInfo) => void;
};

const MODES: { value: DocumentSourceMode; label: string; icon: typeof Type }[] = [
  { value: "text", label: "Colar texto", icon: Type },
  { value: "url", label: "Link", icon: Link2 },
];

/** Novo documento a partir de texto colado ou de um link (PDF ou página HTML). */
export function DocumentSourceDialog({ mode, onModeChange, ensureAnalysis, onCreated }: DocumentSourceDialogProps) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [urlError, setUrlError] = useState<string | null>(null);
  const createText = useCreateTextDocument();
  const createUrl = useCreateUrlDocument();
  const busy = createText.isPending || createUrl.isPending;

  const close = () => {
    if (busy) return;
    onModeChange(null);
    setError(null);
    setUrlError(null);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setUrlError(null);
    if (mode === "url" && !/^https?:\/\/\S+$/i.test(url.trim())) {
      setUrlError("Use um link completo, começando com http:// ou https://.");
      return;
    }
    if (mode === "text" && !content.trim()) {
      setError("Cole o texto do documento.");
      return;
    }
    try {
      const analysisId = await ensureAnalysis();
      const doc =
        mode === "url"
          ? await createUrl.mutateAsync({ analysis_id: analysisId, url: url.trim() })
          : await createText.mutateAsync({ analysis_id: analysisId, title: title.trim() || null, content });
      setTitle("");
      setContent("");
      setUrl("");
      onModeChange(null);
      onCreated(doc);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <Dialog
      open={mode !== null}
      onOpenChange={(open) => !open && close()}
      title="Adicionar documento"
      description={
        mode === "url"
          ? "O Grifo baixa o PDF ou a página HTML do link e lê o texto."
          : "Cole o texto de um contrato, edital ou regulamento."
      }
      className="w-[600px]"
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div role="tablist" aria-label="Origem do documento" className="flex gap-1 rounded-md bg-surface-muted p-1">
          {MODES.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={mode === value}
              disabled={busy}
              onClick={() => {
                setError(null);
                onModeChange(value);
              }}
              className={cn(
                "flex h-8 flex-1 items-center justify-center gap-1.5 rounded-sm text-[13px] font-medium text-foreground-muted transition-colors duration-150 ease-out",
                mode === value && "bg-surface text-foreground shadow-sm",
              )}
            >
              <Icon size={14} strokeWidth={1.75} aria-hidden />
              {label}
            </button>
          ))}
        </div>

        {mode === "url" ? (
          <Field
            label="Link"
            htmlFor="doc-url"
            hint="Apenas endereços públicos. Páginas que exigem login não funcionam."
            error={urlError}
          >
            <Input
              id="doc-url"
              type="url"
              inputMode="url"
              autoFocus
              placeholder="https://www.exemplo.gov.br/edital.pdf"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              aria-invalid={!!urlError || undefined}
              aria-describedby={fieldDescribedBy("doc-url", { hint: true, error: urlError })}
              disabled={busy}
            />
          </Field>
        ) : (
          <>
            <Field label="Título (opcional)" htmlFor="doc-title">
              <Input
                id="doc-title"
                maxLength={200}
                placeholder="Usa a primeira linha do texto se ficar vazio"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={busy}
              />
            </Field>
            <Field label="Texto" htmlFor="doc-content">
              <Textarea
                id="doc-content"
                autoFocus
                rows={12}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                className="max-h-[50vh] font-mono text-[13px]"
                disabled={busy}
              />
            </Field>
          </>
        )}

        {error && <FormError>{error}</FormError>}

        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={close} disabled={busy}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" loading={busy}>
            {mode === "url" ? (busy ? "Baixando…" : "Baixar e analisar") : "Analisar texto"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
