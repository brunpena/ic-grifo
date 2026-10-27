"use client";

import { AlertCircle, Database, FileSpreadsheet, Trash2, X } from "lucide-react";
import { useRef, useState } from "react";
import { IconButton } from "@/components/ui/icon-button";
import { ProgressBar } from "@/components/ui/progress-bar";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { type Dataset, isCsvFile, useDeleteDataset, useUploadDataset } from "@/lib/analyses";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

type Upload = { id: number; name: string; size: number; sent: number; error?: string };

type DatasetUploaderProps = {
  datasets: Dataset[];
  /** Devolve a análise onde gravar as bases, criando-a no primeiro envio. */
  ensureAnalysis: () => Promise<string>;
  className?: string;
};

let nextUpload = 0;

const plural = (n: number, one: string, many: string) => `${n.toLocaleString("pt-BR")} ${n === 1 ? one : many}`;

const formatBytes = (bytes: number) => {
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toLocaleString("pt-BR", { maximumFractionDigits: unit ? 1 : 0 })} ${units[unit]}`;
};

/** Texto do status do envio: a porcentagem e, ao fim, a espera pela resposta do servidor. */
function uploadStatus(u: Upload) {
  if (u.error) return u.error;
  if (u.sent < u.size) {
    const percent = Math.floor((u.sent / u.size) * 100);
    return `Enviando… ${percent}% (${formatBytes(u.sent)} de ${formatBytes(u.size)})`;
  }
  return "Concluindo o envio…";
}

/** Envio de várias bases em CSV. As linhas ficam só no servidor: aqui aparecem o nome, a
 * situação da leitura e o tamanho detectado, com opção de remover. */
export function DatasetUploader({ datasets, ensureAnalysis, className }: DatasetUploaderProps) {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [removing, setRemoving] = useState<string | null>(null);
  const upload = useUploadDataset();
  const remove = useDeleteDataset();

  const sendFiles = async (files: File[]) => {
    if (!files.length) return;
    const accepted = files.filter(isCsvFile);
    const rejected = files.filter((f) => !isCsvFile(f));
    const failed = (name: string, error: string): Upload => ({ id: ++nextUpload, name, size: 0, sent: 0, error });
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
        setUploads((list) => [...list, { id, name: file.name, size: file.size, sent: 0 }]);
        try {
          await upload.mutateAsync({
            analysisId,
            file,
            // O total do envio inclui o envelope do formulário; a barra segue o tamanho do arquivo.
            onProgress: ({ loaded, total }) => {
              const sent = loaded >= total ? file.size : Math.floor((loaded / total) * file.size);
              setUploads((list) => list.map((u) => (u.id === id ? { ...u, sent } : u)));
            },
          });
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
        accept=".csv,.tsv,.txt,.crdownload,text/csv"
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
              className={cn(
                "flex items-center gap-3 rounded-lg border px-3 py-2 text-left",
                d.status === "error" ? "border-danger/40 bg-danger-soft" : "border-border bg-surface",
              )}
            >
              {d.status === "processing" ? (
                <Spinner className="shrink-0" />
              ) : d.status === "error" ? (
                <AlertCircle size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-danger" />
              ) : (
                <Database size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-accent" />
              )}
              <div className="flex min-w-0 flex-1 flex-col" role={d.status === "error" ? "alert" : "status"}>
                <span className="truncate text-[13px] font-medium" title={d.filename}>
                  {d.name}
                </span>
                <span
                  className={cn("text-xs tabular-nums", d.status === "error" ? "text-danger" : "text-foreground-subtle")}
                >
                  {d.status === "processing"
                    ? `Carregando a base no servidor… (${formatBytes(d.size_bytes)})`
                    : d.status === "error"
                      ? (d.status_message ?? "Não foi possível ler a base.")
                      : `${plural(d.row_count, "linha", "linhas")} · ${plural(d.columns.length, "coluna", "colunas")}`}
                </span>
                {d.original_size_bytes != null && d.original_size_bytes > d.size_bytes && (
                  <p className="mt-1 text-xs text-danger">Base parcial: o limite do armazenamento cortou o arquivo. A validação cobre somente as linhas guardadas.</p>
                )}
                {d.status === "ready" && (
                  <details className="mt-1 text-xs">
                    <summary className="cursor-pointer text-accent">Significado das colunas (IA)</summary>
                    {d.status_message && <p className="mt-2 text-foreground-muted">{d.status_message}</p>}
                    <dl className="mt-2 space-y-3">
                      {d.columns.map((column) => (
                        <div key={column.name}>
                          <dt className="font-medium">{column.name}</dt>
                          <dd className="text-foreground-muted">{column.semantic?.meaning ?? "Interpretação pendente"}</dd>
                          {column.semantic && <dd className="text-foreground-subtle">Confiança {column.semantic.confidence === "high" ? "alta" : column.semantic.confidence === "medium" ? "média" : "baixa"}{column.semantic.unit ? ` · ${column.semantic.unit}` : ""}{column.semantic.event ? ` · ${column.semantic.event}` : ""}. {column.semantic.reason}</dd>}
                        </div>
                      ))}
                    </dl>
                  </details>
                )}
              </div>
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
                <span className={cn("text-xs tabular-nums", u.error ? "text-danger" : "text-foreground-subtle")}>
                  {uploadStatus(u)}
                </span>
                {!u.error && u.sent < u.size && (
                  <ProgressBar value={u.sent} max={u.size} label={`Envio de ${u.name}`} className="mt-1.5" />
                )}
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

    </div>
  );
}
