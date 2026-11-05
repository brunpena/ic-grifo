import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/** Larguras alternadas para as células não parecerem uma grade uniforme. */
const WIDTHS = ["w-20", "w-14", "w-28", "w-16", "w-24", "w-10", "w-32", "w-12"];
const GENERIC_COLUMNS = 6;

export type LeadingColumn = {
  label: string;
  /** Classe da célula de corpo (ex.: largura mínima da coluna de evidência). */
  cellClassName?: string;
  /** Classe do placeholder dentro da célula. */
  skeletonClassName?: string;
  sticky?: boolean;
};

const HEAD = "border-b border-border px-3 py-2 text-xs font-medium whitespace-nowrap text-foreground-muted";
const CELL = "border-b border-border px-3 py-2";

/**
 * Tabela de registros enquanto a página ainda não chegou. O cabeçalho já mostra os
 * nomes reais das colunas (guardados do processamento inicial da base); só o corpo
 * fica em placeholder. Sem os nomes, usa colunas genéricas.
 */
export function RecordsTableSkeleton({
  columns,
  leading = [{ label: "Linha", sticky: true, skeletonClassName: "w-8" }],
  rows = 10,
  className,
}: {
  columns: string[] | null;
  leading?: LeadingColumn[];
  rows?: number;
  className?: string;
}) {
  const known = !!columns?.length;
  const names = known ? columns : Array.from({ length: GENERIC_COLUMNS }, (_, i) => `coluna-${i}`);
  return (
    <div role="status" aria-busy className={cn("min-h-0 flex-1 overflow-auto", className)}>
      <span className="sr-only">Carregando registros</span>
      <table aria-hidden className="border-separate border-spacing-0 text-left text-[13px]">
        <thead className="sticky top-0 z-10 bg-surface-muted">
          <tr>
            {leading.map((c) => (
              <th key={c.label} scope="col" className={cn(HEAD, c.sticky && "sticky left-0 z-10 bg-surface-muted")}>
                {c.label}
              </th>
            ))}
            {names.map((name) => (
              <th key={name} scope="col" className={HEAD}>
                {known ? name : <Skeleton className="h-3 w-16" />}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, row) => (
            <tr key={row}>
              {leading.map((c) => (
                <td key={c.label} className={cn(CELL, c.cellClassName, c.sticky && "sticky left-0 bg-surface")}>
                  <Skeleton className={cn("h-3", c.skeletonClassName ?? "w-16")} />
                </td>
              ))}
              {names.map((name, col) => (
                <td key={name} className={CELL}>
                  {/* Pelo menos a largura do nome, para o cabeçalho não pular quando os dados entram. */}
                  <Skeleton className={cn("h-3 min-w-8", WIDTHS[(row * 3 + col) % WIDTHS.length])} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Rodapé de paginação enquanto o total ainda não é conhecido. */
export function PaginationSkeleton() {
  return (
    <div aria-hidden className="flex h-10 shrink-0 items-center gap-2 border-t border-border px-3">
      <Skeleton className="h-3 w-36" />
      <div className="ml-auto flex gap-1">
        <Skeleton className="size-7" />
        <Skeleton className="size-7" />
      </div>
    </div>
  );
}

/** Lista de regras (visão geral da tabela) enquanto as regras carregam. */
export function RulesOverviewSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div role="status" aria-busy className="min-h-0 flex-1 overflow-hidden">
      <span className="sr-only">Carregando regras</span>
      <ul aria-hidden className="divide-y divide-border">
        {Array.from({ length: rows }, (_, i) => (
          <li key={i} className="flex items-center gap-3 px-3 py-2.5">
            <Skeleton className="h-6 w-24 shrink-0" />
            <span className="flex min-w-0 flex-1 flex-col gap-1.5">
              <Skeleton className={cn("h-3", i % 2 ? "w-3/5" : "w-4/5")} />
              <Skeleton className={cn("h-2.5", i % 3 ? "w-2/5" : "w-1/2")} />
            </span>
            <Skeleton className="h-3 w-28" />
          </li>
        ))}
      </ul>
    </div>
  );
}
