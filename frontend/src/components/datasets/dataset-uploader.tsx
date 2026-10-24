"use client";

import { AlertCircle, Database, Eye, FileSpreadsheet, Trash2, X } from "lucide-react";
import { useRef, useState } from "react";
import { IconButton } from "@/components/ui/icon-button";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { type Dataset, isCsvFile, useDeleteDataset, useUploadDataset } from "@/lib/analyses";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DatasetPreviewDialog } from "./dataset-preview";

type Upload = { id: number; name: string; error?: string };

type DatasetUploaderProps = {
  datasets: Dataset[];
  /** Devolve a análise onde gravar as bases, criando-a no primeiro envio. */
  ensureAnalysis: () => Promise<string>;
  className?: string;
};

let nextUpload = 0;

const plural = (n: number, one: string, many: string) => `${n.toLocaleString("pt-BR")} ${n === 1 ? one : many}`;

/** Envio de várias bases em CSV, com prévia do schema detectado e opção de remover. */
export function DatasetUploader({ datasets, ensureAnalysis, className }: DatasetUploaderProps) {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [preview, setPreview] = useState<Dataset | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const upload = useUploadDataset();
  const remove = useDeleteDataset();

  const sendFiles = async (files: File[]) => {
    if (!files.length) return;
    const accepted = files.filter(isCsvFile);
    const rejected = files.filter((f) => !isCsvFile(f));
    const failed = (name: string, error: string): Upload => ({ id: ++nextUpload, name, error });
    if (rejected.length) {
      setUploads((list) => [...list, ...rejected.map((f) => failed(f.name, "Não é um arquivo CSV."))]);
    }
    if (!accepted.length) return;

    let analysisId: string;
    try {
      analysisId = await ensureAnalysis();
    } catch (error) {
      toast({ title: "Não foi possível criar a análise", description: errorMessage(error), variant: "error" });
      return;
    }
    await Promise.all(
      accepted.map(async (file) => {
        const id = ++nextUpload;
        setUploads((list) => [...list, { id, name: file.name }]);
        try {
          await upload.mutateAsync({ analysisId, file });
          setUploads((list) => list.filter((u) => u.id !== id));
        } catch (error) {
          setUploads((list) => list.map((u) => (u.id === id ? { ...u, error: errorMessage(error) } : u)));
        }
      }),
    );
  };

  const removeDataset = (dataset: Dataset) => {
    setRemoving(dataset.id);
    remove.mutate(dataset, {
      onError: (error) => toast({ title: "Não foi possível remover", description: errorMessage(error), variant: "error" }),
      onSettled: () => setRemoving(null),
    });
  };

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragEnter={(e) => {
          if (!e.dataTransfer.types.includes("Files")) return;
          e.preventDefault();
          e.stopPropagation();
          setDragging(true);
        }}
        onDragOver={(e) => {
          if (!e.dataTransfer.types.includes("Files")) return;
          e.preventDefault();
          e.stopPropagation();
        }}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          // Não deixa o soltar chegar à área de envio de PDF da tela.
          e.stopPropagation();
          setDragging(false);
          void sendFiles(Array.from(e.dataTransfer.files));
        }}
        className={cn(
          "flex w-full items-center gap-3 rounded-lg border-2 border-dashed border-border-strong px-4 py-4 text-left",
          "transition-colors duration-150 ease-out hover:bg-surface-hover",
          dragging && "border-accent bg-accent-soft hover:bg-accent-soft",
        )}
      >
        <FileSpreadsheet
          size={24}
          strokeWidth={1.5}
          aria-hidden
          className={cn("shrink-0 text-foreground-subtle", dragging && "text-accent")}
        />
        <span className="flex flex-col gap-0.5">
          <span className="text-sm font-medium">Arraste os CSVs ou clique para escolher</span>
          <span className="text-xs text-foreground-subtle">Uma ou mais bases. Separador e tipos são detectados sozinhos.</span>
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".csv,.tsv,.txt,text/csv"
        className="sr-only"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          void sendFiles(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />

      {(datasets.length > 0 || uploads.length > 0) && (
        <ul className="flex flex-col gap-2" aria-label="Bases enviadas">
          {datasets.map((d) => (
            <li
              key={d.id}
              className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-left"
            >
              <Database size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-accent" />
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[13px] font-medium" title={d.filename}>
                  {d.name}
                </span>
                <span className="text-xs text-foreground-subtle tabular-nums">
                  {plural(d.row_count, "linha", "linhas")} · {plural(d.columns.length, "coluna", "colunas")}
                </span>
              </div>
              <IconButton
                aria-label={`Ver prévia de ${d.name}`}
                icon={<Eye size={16} strokeWidth={1.75} aria-hidden />}
                onClick={() => setPreview(d)}
              />
              <IconButton
                aria-label={`Remover ${d.name}`}
                icon={<Trash2 size={16} strokeWidth={1.75} aria-hidden />}
                loading={removing === d.id}
                onClick={() => removeDataset(d)}
              />
            </li>
          ))}
          {uploads.map((u) => (
            <li
              key={u.id}
              className={cn(
                "flex items-center gap-3 rounded-lg border px-3 py-2 text-left",
                u.error ? "border-danger/40 bg-danger-soft" : "border-border bg-surface",
              )}
            >
              {u.error ? (
                <AlertCircle size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-danger" />
              ) : (
                <Spinner className="shrink-0" />
              )}
              <div className="flex min-w-0 flex-1 flex-col" role={u.error ? "alert" : "status"}>
                <span className="truncate text-[13px] font-medium">{u.name}</span>
                <span className={cn("text-xs", u.error ? "text-danger" : "text-foreground-subtle")}>
                  {u.error ?? "Lendo a base…"}
                </span>
              </div>
              {u.error && (
                <IconButton
                  aria-label="Dispensar"
                  icon={<X size={16} strokeWidth={1.75} aria-hidden />}
                  onClick={() => setUploads((list) => list.filter((x) => x.id !== u.id))}
                />
              )}
            </li>
          ))}
        </ul>
      )}

      <DatasetPreviewDialog dataset={preview} onClose={() => setPreview(null)} />
    </div>
  );
}
