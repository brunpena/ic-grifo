"use client";

import { AlertTriangle, ArrowLeft, ChevronLeft, ChevronRight, Database, FileSpreadsheet, Pencil, SearchX, X } from "lucide-react";
import { useState } from "react";
import { RuleTypeBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { IconButton } from "@/components/ui/icon-button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import type { Rule } from "@/lib/documents";
import { describeQuery, useRuleRecords } from "@/lib/queries";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 100;
const number = (n: number) => n.toLocaleString("pt-BR");

type RecordsPanelProps = {
  rules: Rule[];
  /** Regra selecionada (a mesma da lista de regras e do grifo no documento). */
  selectedRuleId: string | null;
  /** Selecionar uma regra também rola o documento até o trecho dela. */
  onSelectRule: (ruleId: string | null) => void;
  hasDatasets: boolean;
  onEditQuery: (rule: Rule) => void;
  /** Esconde o painel (some quando não há como fechar, ex.: no celular). */
  onClose?: () => void;
  className?: string;
};

/** Registros das bases encontrados pela busca de cada regra. */
export function RecordsPanel({
  rules,
  selectedRuleId,
  onSelectRule,
  hasDatasets,
  onEditQuery,
  onClose,
  className,
}: RecordsPanelProps) {
  const selected = rules.find((r) => r.id === selectedRuleId) ?? null;
  const withQuery = rules.filter((r) => r.query);

  return (
    <section aria-label="Registros encontrados" className={cn("flex h-full min-h-0 flex-col bg-surface", className)}>
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-3">
        <FileSpreadsheet size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-accent" />
        <span className="text-[13px] font-medium">Registros</span>
        {hasDatasets && withQuery.length > 0 && (
          <Select
            aria-label="Filtrar registros por regra"
            value={selected?.id ?? ""}
            onChange={(e) => onSelectRule(e.target.value || null)}
            className="ml-auto w-56 max-w-[60%] [&_select]:h-8 [&_select]:text-[13px]"
          >
            <option value="">Todas as regras</option>
            {selected && !selected.query && <option value={selected.id}>{selected.summary}</option>}
            {withQuery.map((r) => (
              <option key={r.id} value={r.id}>
                {r.summary}
              </option>
            ))}
          </Select>
        )}
        {onClose && (
          <IconButton
            aria-label="Esconder tabela"
            icon={<X size={16} strokeWidth={1.75} aria-hidden />}
            onClick={onClose}
            tooltipSide="bottom"
            className={cn(!(hasDatasets && withQuery.length > 0) && "ml-auto")}
          />
        )}
      </div>

      {!hasDatasets ? (
        <EmptyState
          icon={Database}
          title="Nenhuma base de dados"
          description="Envie um CSV na tela inicial da análise para buscar os registros de cada regra."
          className="flex-1"
        />
      ) : selected ? (
        <RuleRecords key={selected.id} rule={selected} onBack={() => onSelectRule(null)} onEditQuery={onEditQuery} />
      ) : (
        <RulesOverview rules={rules} onSelectRule={onSelectRule} />
      )}
    </section>
  );
}

/** Sem regra escolhida: as regras com busca e quantos registros cada uma encontrou. */
function RulesOverview({ rules, onSelectRule }: { rules: Rule[]; onSelectRule: (id: string) => void }) {
  const withQuery = rules.filter((r) => r.query);
  if (!withQuery.length) {
    return (
      <EmptyState
        icon={SearchX}
        title="Nenhuma regra com busca"
        description="Use “Gerar buscas com IA” na lista de regras ou crie a busca de uma regra pela coluna “Busca na base”."
        className="flex-1"
      />
    );
  }
  const without = rules.length - withQuery.length;
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <ul className="divide-y divide-border">
        {withQuery.map((r) => {
          const query = r.query!;
          return (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => onSelectRule(r.id)}
                className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors duration-150 ease-out hover:bg-surface-hover"
              >
                <RuleTypeBadge type={r.type} className="shrink-0" />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[13px] font-medium">{r.summary}</span>
                  <span className="truncate text-xs text-foreground-subtle">
                    {query.dataset_name ?? "base removida"} · {describeQuery(query.query)}
                  </span>
                </span>
                {query.state === "ok" ? (
                  <span className="shrink-0 rounded-sm bg-accent-soft px-2 py-0.5 font-mono text-xs text-accent tabular-nums">
                    {number(query.match_count ?? 0)}
                  </span>
                ) : (
                  <span className="shrink-0 rounded-sm bg-danger-soft px-2 py-0.5 text-xs text-danger">
                    {query.state === "erro" ? "erro" : "pendente"}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
      {without > 0 && (
        <p className="px-3 py-3 text-xs text-foreground-subtle">
          {without} {without === 1 ? "regra não tem busca" : "regras não têm busca"} (sem relação com as bases ou ainda não geradas).
        </p>
      )}
    </div>
  );
}

function RuleRecords({ rule, onBack, onEditQuery }: { rule: Rule; onBack: () => void; onEditQuery: (rule: Rule) => void }) {
  const [offset, setOffset] = useState(0);
  const query = rule.query;
  const ok = query?.state === "ok";
  const records = useRuleRecords(rule.id, offset, PAGE_SIZE, ok);
  const data = records.data;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 items-start gap-2 border-b border-border px-3 py-2">
        <IconButton
          aria-label="Ver todas as regras"
          icon={<ArrowLeft size={16} strokeWidth={1.75} aria-hidden />}
          onClick={onBack}
          className="-ml-1"
        />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-[13px] font-medium" title={rule.summary}>
            {rule.summary}
          </span>
          <span className="text-xs text-foreground-subtle">
            {query
              ? `${query.dataset_name ?? "base removida"} · ${describeQuery(query.query)}`
              : "Esta regra ainda não tem busca nas bases."}
          </span>
        </div>
        <Button size="sm" variant="ghost" icon={<Pencil size={14} strokeWidth={1.75} aria-hidden />} onClick={() => onEditQuery(rule)}>
          {query ? "Editar busca" : "Criar busca"}
        </Button>
      </div>

      {!query ? (
        <EmptyState icon={SearchX} title="Sem busca" description="Crie a busca para ver os registros desta regra." className="flex-1" />
      ) : query.state === "erro" ? (
        <EmptyState
          icon={AlertTriangle}
          title="A busca tem um erro"
          description={query.error}
          action={
            <Button size="sm" variant="primary" onClick={() => onEditQuery(rule)}>
              Corrigir busca
            </Button>
          }
          className="flex-1"
        />
      ) : records.isError ? (
        <EmptyState
          icon={AlertTriangle}
          title="Não foi possível carregar os registros"
          description={errorMessage(records.error)}
          action={
            <Button size="sm" onClick={() => void records.refetch()}>
              Tentar de novo
            </Button>
          }
          className="flex-1"
        />
      ) : data && data.total === 0 ? (
        <EmptyState
          icon={SearchX}
          title="Nenhum registro encontrado"
          description="Nenhuma linha da base atende a esta busca. Revise as condições se esperava resultados."
          className="flex-1"
        />
      ) : (
        <>
          <div className="min-h-0 flex-1 overflow-auto" aria-busy={records.isFetching || undefined}>
            <table className="border-separate border-spacing-0 text-left text-[13px]">
              <thead className="sticky top-0 z-10 bg-surface-muted">
                <tr>
                  <th scope="col" className="sticky left-0 z-10 border-b border-border bg-surface-muted px-3 py-2 text-xs font-medium text-foreground-muted">
                    Linha
                  </th>
                  {(data?.columns ?? []).map((c) => (
                    <th key={c} scope="col" className="border-b border-border px-3 py-2 text-xs font-medium whitespace-nowrap text-foreground-muted">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className={cn(records.isPlaceholderData && "opacity-60")}>
                {data
                  ? data.rows.map((row) => (
                      <tr key={row.index} className="hover:bg-surface-hover">
                        <td className="sticky left-0 border-b border-border bg-surface px-3 py-1.5 font-mono text-xs text-foreground-subtle tabular-nums">
                          {number(row.index + 1)}
                        </td>
                        {row.values.map((cell, i) => (
                          <td key={i} className="border-b border-border px-3 py-1.5 whitespace-nowrap">
                            {cell === null ? (
                              <span className="text-foreground-subtle">—</span>
                            ) : (
                              <span className="block max-w-64 truncate" title={cell}>
                                {cell}
                              </span>
                            )}
                          </td>
                        ))}
                      </tr>
                    ))
                  : Array.from({ length: 8 }, (_, i) => (
                      <tr key={i} aria-hidden>
                        <td className="border-b border-border px-3 py-2" colSpan={6}>
                          <Skeleton className="h-3 w-full" />
                        </td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
          {data && (
            <div className="flex h-10 shrink-0 items-center gap-2 border-t border-border px-3 text-xs text-foreground-muted">
              <span className="tabular-nums" aria-live="polite">
                {number(offset + 1)}–{number(Math.min(offset + PAGE_SIZE, data.total))} de {number(data.total)}{" "}
                {data.total === 1 ? "registro" : "registros"}
              </span>
              <div className="ml-auto flex">
                <IconButton
                  aria-label="Página anterior"
                  icon={<ChevronLeft size={16} strokeWidth={1.75} aria-hidden />}
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                />
                <IconButton
                  aria-label="Próxima página"
                  icon={<ChevronRight size={16} strokeWidth={1.75} aria-hidden />}
                  disabled={offset + PAGE_SIZE >= data.total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
