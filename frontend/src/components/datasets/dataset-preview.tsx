"use client";

import { Dialog } from "@/components/ui/dialog";
import { COLUMN_TYPE_LABELS, type Dataset } from "@/lib/analyses";

const DELIMITER_LABELS: Record<string, string> = {
  ",": "vírgula",
  ";": "ponto e vírgula",
  "\t": "tab",
  "|": "barra vertical",
};

/** Schema detectado (colunas e tipos) e as primeiras linhas de uma base. */
export function DatasetPreviewDialog({ dataset, onClose }: { dataset: Dataset | null; onClose: () => void }) {
  return (
    <Dialog
      open={!!dataset}
      onOpenChange={(open) => !open && onClose()}
      title={dataset?.name ?? ""}
      description={
        dataset &&
        `${dataset.filename} · ${dataset.row_count.toLocaleString("pt-BR")} linhas · separador ${
          DELIMITER_LABELS[dataset.delimiter] ?? dataset.delimiter
        } · ${dataset.encoding}`
      }
      className="w-[880px]"
    >
      {dataset && (
        <div className="flex min-w-0 flex-col gap-2">
          <div className="max-h-[60vh] overflow-auto rounded-md border border-border">
            <table className="border-separate border-spacing-0 text-left text-[13px]">
              <thead className="sticky top-0 z-10 bg-surface-muted">
                <tr>
                  {dataset.columns.map((c) => (
                    <th key={c.name} scope="col" className="border-b border-border px-3 py-2 align-top font-medium">
                      <span className="block max-w-56 truncate" title={c.name}>
                        {c.name}
                      </span>
                      <span className="block text-xs font-normal text-foreground-subtle">
                        {COLUMN_TYPE_LABELS[c.type]}
                        {c.null_count > 0 && ` · ${c.null_count.toLocaleString("pt-BR")} vazias`}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dataset.sample_rows.map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, j) => (
                      <td key={j} className="border-b border-border px-3 py-1.5 whitespace-nowrap">
                        {cell === null ? (
                          <span className="text-foreground-subtle">—</span>
                        ) : (
                          <span className="block max-w-56 truncate" title={cell}>
                            {cell}
                          </span>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-foreground-subtle">
            Mostrando {dataset.sample_rows.length} de {dataset.row_count.toLocaleString("pt-BR")} linhas. O schema e
            essa amostra vão como contexto para a IA.
          </p>
        </div>
      )}
    </Dialog>
  );
}
