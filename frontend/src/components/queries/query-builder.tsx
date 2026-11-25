"use client";

import { Braces, ListFilter, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { IconButton } from "@/components/ui/icon-button";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { COLUMN_TYPE_LABELS, type ColumnType, type Dataset, type DatasetColumn } from "@/lib/analyses";
import { useT } from "@/lib/i18n";
import {
  type ConditionValue,
  isFlat,
  LIST_OPERATORS,
  NO_VALUE_OPERATORS,
  OPERATOR_LABELS,
  OPERATORS_BY_TYPE,
  type QueryCondition,
  type QueryOperator,
  type StructuredQuery,
} from "@/lib/queries";
import { cn } from "@/lib/utils";

/** Condição no formulário: os valores ficam como texto até salvar. */
type DraftCondition = { key: number; column: string; op: QueryOperator; value: string; value2: string };
type Draft = { dataset: string; logic: "and" | "or"; conditions: DraftCondition[] };

let nextKey = 0;

const asText = (v: ConditionValue | undefined): string =>
  v == null ? "" : Array.isArray(v) ? v.map(asText).join("; ") : String(v);

function toDraft(query: StructuredQuery): Draft {
  return {
    dataset: query.dataset,
    logic: query.logic,
    conditions: (query.conditions ?? []).filter((c): c is QueryCondition => !("conditions" in c)).map((c) => ({
      key: ++nextKey,
      column: c.column,
      op: c.op,
      value: c.op === "between" && Array.isArray(c.value) ? asText(c.value[0]) : asText(c.value),
      value2: c.op === "between" && Array.isArray(c.value) ? asText(c.value[1]) : "",
    })),
  };
}

function convert(type: ColumnType | undefined, raw: string): string | number | boolean {
  const text = raw.trim();
  if ((type === "integer" || type === "decimal") && text !== "" && Number.isFinite(Number(text))) return Number(text);
  if (type === "boolean" && (text === "true" || text === "false")) return text === "true";
  return text;
}

function fromDraft(draft: Draft, columns: DatasetColumn[]): StructuredQuery {
  const typeOf = (name: string) => columns.find((c) => c.name === name)?.type;
  return {
    dataset: draft.dataset,
    logic: draft.logic,
    conditions: draft.conditions.map(({ column, op, value, value2 }) => {
      const type = typeOf(column);
      if (NO_VALUE_OPERATORS.has(op)) return { column, op };
      if (op === "between") return { column, op, value: [convert(type, value), convert(type, value2)] };
      if (LIST_OPERATORS.has(op)) {
        const items = value.split(";").map((v) => v.trim()).filter(Boolean);
        return { column, op, value: items.map((v) => convert(type, v)) };
      }
      return { column, op, value: convert(type, value) };
    }),
  };
}

export type QueryBuilderState = ReturnType<typeof useQueryBuilder>;

/**
 * Rascunho de uma busca, editável no formulário (condições simples) ou em JSON (grupos).
 * `build()` devolve a busca pronta ou `null`, com o motivo em `error`.
 */
export function useQueryBuilder(initial: StructuredQuery, datasets: Dataset[]) {
  const t = useT();
  const [mode, setMode] = useState<"form" | "json">(isFlat(initial) ? "form" : "json");
  const [draft, setDraft] = useState<Draft>(() => toDraft(initial));
  const [json, setJson] = useState(() => JSON.stringify(initial, null, 2));
  const [error, setError] = useState<string | null>(null);
  const dataset = datasets.find((d) => d.name === draft.dataset);
  const columns = dataset?.columns ?? [];

  const switchMode = (next: "form" | "json") => {
    setError(null);
    if (next === "json") {
      setJson(JSON.stringify(fromDraft(draft, columns), null, 2));
    } else {
      try {
        const parsed = JSON.parse(json) as StructuredQuery;
        if (!isFlat(parsed)) {
          setError(t("Buscas com grupos (condições dentro de condições) só podem ser editadas em JSON."));
          return;
        }
        setDraft(toDraft(parsed));
      } catch {
        setError(t("O JSON não é válido."));
        return;
      }
    }
    setMode(next);
  };

  const build = (): StructuredQuery | null => {
    setError(null);
    if (mode === "json") {
      try {
        return JSON.parse(json) as StructuredQuery;
      } catch {
        setError(t("O JSON não é válido."));
        return null;
      }
    }
    if (!draft.dataset) {
      setError(t("Escolha a base de dados."));
      return null;
    }
    return fromDraft(draft, columns);
  };

  return { mode, switchMode, draft, setDraft, json, setJson, error, setError, dataset, columns, build };
}

type QueryBuilderProps = {
  state: QueryBuilderState;
  datasets: Dataset[];
  /** Avisa a cada mudança (ex.: para descartar uma prévia de contagem já desatualizada). */
  onEdit?: () => void;
  /** Campos em uma coluna, para painéis estreitos. */
  compact?: boolean;
};

/** Formulário da busca: base, lógica e condições, ou o JSON da busca. */
export function QueryBuilder({ state, datasets, onEdit, compact }: QueryBuilderProps) {
  const t = useT();
  const { mode, switchMode, draft, json, dataset, columns } = state;
  const columnOf = (name: string) => columns.find((c) => c.name === name);
  const setDraft: typeof state.setDraft = (value) => {
    state.setDraft(value);
    onEdit?.();
  };
  const update = (key: number, changes: Partial<DraftCondition>) =>
    setDraft((d) => ({ ...d, conditions: d.conditions.map((c) => (c.key === key ? { ...c, ...changes } : c)) }));

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-foreground-subtle">{t("Encontre os registros aos quais esta regra se aplica.")}</p>
        <Button
          size="sm"
          variant="ghost"
          icon={mode === "form" ? <Braces size={16} strokeWidth={1.75} aria-hidden /> : <ListFilter size={16} strokeWidth={1.75} aria-hidden />}
          onClick={() => switchMode(mode === "form" ? "json" : "form")}
        >
          {mode === "form" ? t("Editar como JSON") : t("Editar no formulário")}
        </Button>
      </div>

      {mode === "json" ? (
        <Field label={t("Busca (JSON)")} htmlFor="query-json" hint={t("Formato: dataset, logic (and/or) e conditions.")}>
          <Textarea
            id="query-json"
            rows={compact ? 10 : 14}
            value={json}
            onChange={(e) => {
              state.setJson(e.target.value);
              onEdit?.();
            }}
            spellCheck={false}
            className="font-mono text-xs"
          />
        </Field>
      ) : (
        <>
          <div className={cn("grid gap-3", !compact && "sm:grid-cols-2")}>
            <Field label={t("Base de dados")} htmlFor="query-dataset">
              <Select
                id="query-dataset"
                value={draft.dataset}
                onChange={(e) => setDraft({ ...draft, dataset: e.target.value, conditions: [] })}
              >
                {!dataset && <option value="">{draft.dataset ? t("{name} (removida)", { name: draft.dataset }) : t("Escolha a base")}</option>}
                {datasets.map((d) => (
                  <option key={d.id} value={d.name}>
                    {d.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t("Registros que atendem a")} htmlFor="query-logic">
              <Select
                id="query-logic"
                value={draft.logic}
                onChange={(e) => setDraft({ ...draft, logic: e.target.value === "or" ? "or" : "and" })}
              >
                <option value="and">{t("todas as condições")}</option>
                <option value="or">{t("qualquer condição")}</option>
              </Select>
            </Field>
          </div>

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1.5 text-[13px] font-medium">{t("Condições")}</legend>
            {draft.conditions.length === 0 && (
              <p className="rounded-md border border-dashed border-border px-3 py-2 text-[13px] text-foreground-muted">
                {t("Sem condições, a busca traz todos os registros da base.")}
              </p>
            )}
            {draft.conditions.map((c, index) => {
              const column = columnOf(c.column);
              const operators = column ? OPERATORS_BY_TYPE[column.type] : [];
              return (
                <div key={c.key} className="flex flex-wrap items-start gap-2 rounded-md bg-surface-muted p-2">
                  <Select
                    aria-label={t("Coluna da condição {n}", { n: index + 1 })}
                    value={column ? c.column : ""}
                    onChange={(e) => {
                      const next = columnOf(e.target.value);
                      const allowed = next ? OPERATORS_BY_TYPE[next.type] : [];
                      update(c.key, {
                        column: e.target.value,
                        op: allowed.includes(c.op) ? c.op : (allowed[0] ?? "eq"),
                        value: "",
                        value2: "",
                      });
                    }}
                    className="min-w-40 flex-1"
                  >
                    {!column && <option value="">{c.column ? t("{name} (não existe)", { name: c.column }) : t("Coluna")}</option>}
                    {columns.map((col) => (
                      <option key={col.name} value={col.name}>
                        {col.name} · {t(COLUMN_TYPE_LABELS[col.type])}
                      </option>
                    ))}
                  </Select>
                  <Select
                    aria-label={t("Operador da condição {n}", { n: index + 1 })}
                    value={c.op}
                    onChange={(e) => update(c.key, { op: e.target.value as QueryOperator })}
                    className="w-44"
                    disabled={!column}
                  >
                    {(operators.length ? operators : [c.op]).map((op) => (
                      <option key={op} value={op}>
                        {t(OPERATOR_LABELS[op])}
                      </option>
                    ))}
                  </Select>
                  {!NO_VALUE_OPERATORS.has(c.op) && (
                    <ValueInputs condition={c} column={column} index={index} onChange={(changes) => update(c.key, changes)} />
                  )}
                  <IconButton
                    aria-label={t("Remover condição {n}", { n: index + 1 })}
                    icon={<Trash2 size={16} strokeWidth={1.75} aria-hidden />}
                    onClick={() => setDraft((d) => ({ ...d, conditions: d.conditions.filter((x) => x.key !== c.key) }))}
                    className="mt-0.5"
                  />
                </div>
              );
            })}
            <Button
              size="sm"
              variant="ghost"
              icon={<Plus size={16} strokeWidth={1.75} aria-hidden />}
              disabled={!dataset}
              onClick={() => {
                const first = columns[0];
                if (!first) return;
                setDraft((d) => ({
                  ...d,
                  conditions: [
                    ...d.conditions,
                    { key: ++nextKey, column: first.name, op: OPERATORS_BY_TYPE[first.type][0], value: "", value2: "" },
                  ],
                }));
              }}
              className="self-start"
            >
              {t("Adicionar condição")}
            </Button>
          </fieldset>
        </>
      )}
    </div>
  );
}

const INPUT_TYPES: Partial<Record<ColumnType, string>> = {
  integer: "number",
  decimal: "number",
  date: "date",
  datetime: "datetime-local",
};

function ValueInputs({
  condition,
  column,
  index,
  onChange,
}: {
  condition: DraftCondition;
  column: DatasetColumn | undefined;
  index: number;
  onChange: (changes: Partial<DraftCondition>) => void;
}) {
  const t = useT();
  const label = t("Valor da condição {n}", { n: index + 1 });
  const listId = `query-values-${condition.key}`;
  if (column?.type === "boolean") {
    return (
      <Select aria-label={label} value={condition.value} onChange={(e) => onChange({ value: e.target.value })} className="w-32">
        <option value="">—</option>
        <option value="true">{t("sim")}</option>
        <option value="false">{t("não")}</option>
      </Select>
    );
  }
  if (LIST_OPERATORS.has(condition.op) && condition.op !== "between") {
    return (
      <Input
        aria-label={label}
        value={condition.value}
        onChange={(e) => onChange({ value: e.target.value })}
        placeholder={t("Valores separados por ;")}
        title={column?.values.length ? t("Valores da base: {values}", { values: column.values.join("; ") }) : undefined}
        className="min-w-40 flex-1"
      />
    );
  }
  const type = (column && INPUT_TYPES[column.type]) ?? "text";
  const step = column?.type === "decimal" ? "any" : undefined;
  return (
    <div className="flex min-w-40 flex-1 items-center gap-2">
      <Input
        aria-label={condition.op === "between" ? t("{label} (mínimo)", { label }) : label}
        type={type}
        step={step}
        list={column?.values.length ? listId : undefined}
        value={condition.value}
        onChange={(e) => onChange({ value: e.target.value })}
      />
      {condition.op === "between" && (
        <>
          <span className="text-xs text-foreground-subtle">{t("e")}</span>
          <Input
            aria-label={t("{label} (máximo)", { label })}
            type={type}
            step={step}
            value={condition.value2}
            onChange={(e) => onChange({ value2: e.target.value })}
          />
        </>
      )}
      {column?.values.length ? (
        <datalist id={listId}>
          {column.values.map((v) => (
            <option key={v} value={v} />
          ))}
        </datalist>
      ) : null}
    </div>
  );
}
