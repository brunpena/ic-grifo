"use client";

import { AlertTriangle, ArrowLeft, Check, ChevronLeft, ChevronRight, Code, Copy, Database, FileSpreadsheet, Pencil, SearchX, X } from "lucide-react";
import { useState } from "react";
import { RuleTypeBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { IconButton } from "@/components/ui/icon-button";
import { Select } from "@/components/ui/select";
import { errorMessage } from "@/lib/api";
import { knownColumns } from "@/lib/column-cache";
import type { Rule } from "@/lib/documents";
import { useT } from "@/lib/i18n";
import { describeQuery, useRuleRecords } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { ValidationDetails } from "@/components/validation/validation-details";
import { PaginationSkeleton, RecordsTableSkeleton, RulesOverviewSkeleton } from "./records-skeleton";

const PAGE_SIZE = 100;

type RecordsPanelProps = {
  rules: Rule[];
  /** Regra selecionada (a mesma da lista de regras e do grifo no documento). */
  selectedRuleId: string | null;
  /** Selecionar uma regra também rola o documento até o trecho dela. */
  onSelectRule: (ruleId: string | null) => void;
  hasDatasets: boolean;
  /** As regras do documento ainda estão sendo carregadas. */
  rulesLoading?: boolean;
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
  rulesLoading,
  onEditQuery,
  onClose,
  className,
}: RecordsPanelProps) {
  const t = useT();
  const [searchFor, setSearchFor] = useState<string | null>(null);
  const selected = rules.find((r) => r.id === selectedRuleId) ?? null;
  const withQuery = rules.filter((r) => r.query);

  return (
    <section aria-label={t("Registros encontrados")} className={cn("flex h-full min-h-0 flex-col bg-surface", className)}>
      <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-3">
        <FileSpreadsheet size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-accent" />
        <span className="text-[13px] font-medium">{t("Registros")}</span>
        {rules.length > 0 && (
          <Select
            aria-label={t("Filtrar registros por regra")}
            value={selected?.id ?? ""}
            onChange={(e) => onSelectRule(e.target.value || null)}
            className="ml-auto w-56 max-w-[60%] [&_select]:h-8 [&_select]:text-[13px]"
          >
            <option value="">{t("Todas as regras")}</option>

            {rules.map((r) => (
              <option key={r.id} value={r.id}>
                {r.summary}
              </option>
            ))}
          </Select>
        )}
        {selected?.validation && (
          <Button size="sm" variant="ghost" onClick={() => setSearchFor(searchFor === selected.id ? null : selected.id)}>
            {searchFor === selected.id ? t("Ver consulta") : t("Ver validação")}
          </Button>
        )}
        {onClose && (
          <IconButton
            aria-label={t("Esconder tabela")}
            icon={<X size={16} strokeWidth={1.75} aria-hidden />}
            onClick={onClose}
            tooltipSide="bottom"
            className={cn(!(hasDatasets && withQuery.length > 0) && "ml-auto")}
          />
        )}
      </div>

      {rulesLoading && !rules.length ? (
        <RulesOverviewSkeleton />
      ) : selected?.validation && searchFor === selected.id ? (
        <ValidationDetails key={selected.id + selected.validation.checked_at} rule={selected} onBack={() => onSelectRule(null)} />
      ) : !hasDatasets && !rules.some((r) => r.validation) ? (
        <EmptyState
          icon={Database}
          title={t("Nenhuma base de dados")}
          description={t("Envie um CSV na tela inicial da análise para buscar os registros de cada regra.")}
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

/** Visão geral de todas as regras, inclusive as inconclusivas e ainda não avaliadas. */
function RulesOverview({ rules, onSelectRule }: { rules: Rule[]; onSelectRule: (id: string) => void }) {
  const t = useT();
  if (!rules.length) {
    return <EmptyState icon={SearchX} title={t("Nenhuma regra encontrada")} description={t("Grife um trecho do documento e aprove a regra proposta pela IA.")} className="flex-1" />;
  }
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <ul className="divide-y divide-border">
        {rules.map((rule) => (
          <li key={rule.id}>
            <button type="button" onClick={() => onSelectRule(rule.id)} className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors duration-150 ease-out hover:bg-surface-hover">
              <RuleTypeBadge type={rule.type} className="shrink-0" />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[13px] font-medium">{rule.summary}</span>
                <span className="truncate text-xs text-foreground-subtle">{rule.query ? describeQuery(rule.query.query, t) : rule.category === "geral" ? t("Regra geral, sem busca nas bases") : t("Sem consulta para esta regra")}</span>
              </span>
              <span className="text-xs text-foreground-muted">{rule.query?.state === "erro" ? t("Revisar consulta") : rule.query ? t("Selecionar para consultar") : t("Sem consulta")}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RuleRecords({ rule, onBack, onEditQuery }: { rule: Rule; onBack: () => void; onEditQuery: (rule: Rule) => void }) {
  const t = useT();
  const [offset, setOffset] = useState(0);
  const [showSql, setShowSql] = useState(false);
  const query = rule.query;
  const ok = !!query && query.state !== "erro";
  const records = useRuleRecords(rule.id, offset, PAGE_SIZE, ok);
  const data = records.data;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 items-start gap-2 border-b border-border px-3 py-2">
        <IconButton
          aria-label={t("Ver todas as regras")}
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
              ? `${query.dataset_name ?? t("base removida")} · ${describeQuery(query.query, t)}`
              : t("Esta regra ainda não tem busca nas bases.")}
          </span>
        </div>
        {query?.sql_display && (
          <Button
            size="sm"
            variant="ghost"
            icon={<Code size={14} strokeWidth={1.75} aria-hidden />}
            aria-expanded={showSql}
            onClick={() => setShowSql(!showSql)}
          >
            {showSql ? t("Ocultar SQL") : t("Ver SQL")}
          </Button>
        )}
        <Button size="sm" variant="ghost" icon={<Pencil size={14} strokeWidth={1.75} aria-hidden />} onClick={() => onEditQuery(rule)}>
          {query ? t("Editar busca") : t("Criar busca")}
        </Button>
      </div>
      {showSql && query?.sql_display && <SqlPreview sql={query.sql_display} />}

      {!query ? (
        rule.category === "geral" ? (
          <EmptyState
            icon={SearchX}
            title={t("Regra geral")}
            description={t("Esta regra foi registrada sem busca porque não se aplica às bases CSV. Crie uma busca se ela puder ser verificada nos dados.")}
            className="flex-1"
          />
        ) : (
          <EmptyState icon={SearchX} title={t("Sem busca")} description={t("Crie a busca para ver os registros desta regra.")} className="flex-1" />
        )
      ) : query.state === "erro" ? (
        <EmptyState
          icon={AlertTriangle}
          title={t("A busca tem um erro")}
          description={query.error}
          action={
            <Button size="sm" variant="primary" onClick={() => onEditQuery(rule)}>
              {t("Corrigir busca")}
            </Button>
          }
          className="flex-1"
        />
      ) : records.isError ? (
        <EmptyState
          icon={AlertTriangle}
          title={t("Não foi possível carregar os registros")}
          description={errorMessage(records.error, t)}
          action={
            <Button size="sm" onClick={() => void records.refetch()}>
              {t("Tentar de novo")}
            </Button>
          }
          className="flex-1"
        />
      ) : !data ? (
        <>
          <RecordsTableSkeleton columns={knownColumns(query.dataset_id)} />
          <PaginationSkeleton />
        </>
      ) : data.total === 0 ? (
        <EmptyState
          icon={SearchX}
          title={t("Nenhum registro encontrado")}
          description={t("Nenhuma linha da base atende a esta busca. Revise as condições se esperava resultados.")}
          className="flex-1"
        />
      ) : (
        <>
          <div className="min-h-0 flex-1 overflow-auto" aria-busy={records.isFetching || undefined}>
            <table className="border-separate border-spacing-0 text-left text-[13px]">
              <thead className="sticky top-0 z-10 bg-surface-muted">
                <tr>
                  <th scope="col" className="sticky left-0 z-10 border-b border-border bg-surface-muted px-3 py-2 text-xs font-medium text-foreground-muted">
                    {t("Linha")}
                  </th>
                  {data.columns.map((c) => (
                    <th key={c} scope="col" className="border-b border-border px-3 py-2 text-xs font-medium whitespace-nowrap text-foreground-muted">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className={cn(records.isPlaceholderData && "opacity-60")}>
                {data.rows.map((row) => (
                  <tr key={row.index} className="hover:bg-surface-hover">
                    <td className="sticky left-0 border-b border-border bg-surface px-3 py-1.5 font-mono text-xs text-foreground-subtle tabular-nums">
                      {t.number(row.index + 1)}
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
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex h-10 shrink-0 items-center gap-2 border-t border-border px-3 text-xs text-foreground-muted">
              <span className="tabular-nums" aria-live="polite">
                {t.plural(data.total, "{from}–{to} de {n} registro", "{from}–{to} de {n} registros", {
                  from: t.number(offset + 1),
                  to: t.number(Math.min(offset + PAGE_SIZE, data.total)),
                })}
              </span>
              <div className="ml-auto flex">
                <IconButton
                  aria-label={t("Página anterior")}
                  icon={<ChevronLeft size={16} strokeWidth={1.75} aria-hidden />}
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                />
                <IconButton
                  aria-label={t("Próxima página")}
                  icon={<ChevronRight size={16} strokeWidth={1.75} aria-hidden />}
                  disabled={offset + PAGE_SIZE >= data.total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                />
              </div>
            </div>
        </>
      )}
    </div>
  );
}

/** Consulta SQL usada para buscar os registros da regra, com os nomes reais das colunas. */
function SqlPreview({ sql }: { sql: string }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Sem permissão para a área de transferência: o texto continua selecionável.
    }
  };
  return (
    <div className="relative shrink-0 border-b border-border bg-surface-muted">
      <pre aria-label={t("Consulta SQL da busca")} className="max-h-48 overflow-auto px-3 py-2 pr-10 font-mono text-xs leading-relaxed whitespace-pre text-foreground">
        {sql}
      </pre>
      <IconButton
        aria-label={copied ? t("SQL copiada") : t("Copiar SQL")}
        icon={copied ? <Check size={14} strokeWidth={1.75} aria-hidden /> : <Copy size={14} strokeWidth={1.75} aria-hidden />}
        onClick={() => void copy()}
        className="absolute top-1 right-1"
      />
    </div>
  );
}
