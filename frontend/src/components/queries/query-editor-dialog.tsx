"use client";

import { Braces, ListFilter, Plus, Trash2 } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, FormError } from "@/components/ui/field";
import { IconButton } from "@/components/ui/icon-button";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useToast } from "@/components/ui/toast";
import { COLUMN_TYPE_LABELS, type ColumnType, type Dataset, type DatasetColumn } from "@/lib/analyses";
import { errorMessage } from "@/lib/api";
import type { Rule } from "@/lib/documents";
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
  useDeleteRuleQuery,
  useSetRuleQuery,
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

function initialQuery(rule: Rule, datasets: Dataset[]): StructuredQuery {
  if (rule.query) return rule.query.query;
  const related = datasets.find((d) => rule.dataset_ids.includes(d.id)) ?? datasets[0];
  return { dataset: related?.name ?? "", logic: "and", conditions: [] };
}

type QueryEditorDialogProps = {
  rule: Rule | null;
  datasets: Dataset[];
  documentId: string;
  onClose: () => void;
};

/** Edita (ou cria) a busca de uma regra. A validação final é a do back, que explica o erro. */
export function QueryEditorDialog({ rule, datasets, documentId, onClose }: QueryEditorDialogProps) {
  return (
    <Dialog
      open={!!rule}
      onOpenChange={(open) => !open && onClose()}
      title="Busca da regra"
      description={rule?.summary}
      className="w-[760px]"
    >
      {/* Remonta a cada regra: o rascunho começa da busca atual dela. */}
      {rule && <QueryEditorForm key={rule.id} rule={rule} datasets={datasets} documentId={documentId} onClose={onClose} />}
    </Dialog>
  );
}

function QueryEditorForm({ rule, datasets, documentId, onClose }: Omit<QueryEditorDialogProps, "rule"> & { rule: Rule }) {
  const toast = useToast();
  const initial = initialQuery(rule, datasets);
  const [mode, setMode] = useState<"form" | "json">(isFlat(initial) ? "form" : "json");
  const [draft, setDraft] = useState<Draft>(() => toDraft(initial));
  const [json, setJson] = useState(() => JSON.stringify(initial, null, 2));
  const [error, setError] = useState<string | null>(null);
  const save = useSetRuleQuery(documentId);
  const remove = useDeleteRuleQuery(documentId);

  const dataset = datasets.find((d) => d.name === draft.dataset);
  const columns = dataset?.columns ?? [];
  const columnOf = (name: string) => columns.find((c) => c.name === name);

  const update = (key: number, changes: Partial<DraftCondition>) =>
    setDraft((d) => ({ ...d, conditions: d.conditions.map((c) => (c.key === key ? { ...c, ...changes } : c)) }));

  const switchMode = (next: "form" | "json") => {
    setError(null);
    if (next === "json") {
      setJson(JSON.stringify(fromDraft(draft, columns), null, 2));
    } else {
      try {
        const parsed = JSON.parse(json) as StructuredQuery;
        if (!isFlat(parsed)) {
          setError("Buscas com grupos (condições dentro de condições) só podem ser editadas em JSON.");
          return;
        }
        setDraft(toDraft(parsed));
      } catch {
        setError("O JSON não é válido.");
        return;
      }
    }
    setMode(next);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    let query: StructuredQuery;
    if (mode === "json") {
      try {
        query = JSON.parse(json) as StructuredQuery;
      } catch {
        setError("O JSON não é válido.");
        return;
      }
    } else {
      if (!draft.dataset) {
        setError("Escolha a base de dados.");
        return;
      }
      query = fromDraft(draft, columns);
    }
    save.mutate(
      { ruleId: rule.id, query },
      {
        onSuccess: (saved) => {
          const count = saved.query?.match_count ?? 0;
          toast({
            title: "Busca salva",
            description: `${count.toLocaleString("pt-BR")} ${count === 1 ? "registro encontrado" : "registros encontrados"}.`,
            variant: "success",
          });
          onClose();
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  };

  if (!datasets.length) {
    return (
      <p className="text-[13px] text-foreground-muted">
        Esta análise não tem bases de dados. Envie um CSV para transformar a regra em busca.
      </p>
    );
  }

  return (
    <form onSubmit={submit} className="flex min-w-0 flex-col gap-4">
      <blockquote className="max-h-24 overflow-auto border-l-2 border-accent pl-3 text-[13px] text-foreground-muted">
        {rule.excerpt}
      </blockquote>

      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-foreground-subtle">Encontre os registros aos quais esta regra se aplica.</p>
        <Button
          size="sm"
          variant="ghost"
          icon={mode === "form" ? <Braces size={16} strokeWidth={1.75} aria-hidden /> : <ListFilter size={16} strokeWidth={1.75} aria-hidden />}
          onClick={() => switchMode(mode === "form" ? "json" : "form")}
        >
          {mode === "form" ? "Editar como JSON" : "Editar no formulário"}
        </Button>
      </div>

      {mode === "json" ? (
        <Field label="Busca (JSON)" htmlFor="query-json" hint="Formato: dataset, logic (and/or) e conditions.">
          <Textarea
            id="query-json"
            rows={14}
            value={json}
            onChange={(e) => setJson(e.target.value)}
            spellCheck={false}
            className="font-mono text-xs"
          />
        </Field>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Base de dados" htmlFor="query-dataset">
              <Select
                id="query-dataset"
                value={draft.dataset}
                onChange={(e) => setDraft({ ...draft, dataset: e.target.value, conditions: [] })}
              >
                {!dataset && <option value="">{draft.dataset ? `${draft.dataset} (removida)` : "Escolha a base"}</option>}
                {datasets.map((d) => (
                  <option key={d.id} value={d.name}>
                    {d.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Registros que atendem a" htmlFor="query-logic">
              <Select
                id="query-logic"
                value={draft.logic}
                onChange={(e) => setDraft({ ...draft, logic: e.target.value === "or" ? "or" : "and" })}
              >
                <option value="and">todas as condições</option>
                <option value="or">qualquer condição</option>
              </Select>
            </Field>
          </div>

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1.5 text-[13px] font-medium">Condições</legend>
            {draft.conditions.length === 0 && (
              <p className="rounded-md border border-dashed border-border px-3 py-2 text-[13px] text-foreground-muted">
                Sem condições, a busca traz todos os registros da base.
              </p>
            )}
            {draft.conditions.map((c, index) => {
              const column = columnOf(c.column);
              const operators = column ? OPERATORS_BY_TYPE[column.type] : [];
              return (
                <div key={c.key} className="flex flex-wrap items-start gap-2 rounded-md bg-surface-muted p-2">
                  <Select
                    aria-label={`Coluna da condição ${index + 1}`}
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
                    {!column && <option value="">{c.column ? `${c.column} (não existe)` : "Coluna"}</option>}
                    {columns.map((col) => (
                      <option key={col.name} value={col.name}>
                        {col.name} · {COLUMN_TYPE_LABELS[col.type]}
                      </option>
                    ))}
                  </Select>
                  <Select
                    aria-label={`Operador da condição ${index + 1}`}
                    value={c.op}
                    onChange={(e) => update(c.key, { op: e.target.value as QueryOperator })}
                    className="w-44"
                    disabled={!column}
                  >
                    {(operators.length ? operators : [c.op]).map((op) => (
                      <option key={op} value={op}>
                        {OPERATOR_LABELS[op]}
                      </option>
                    ))}
                  </Select>
                  {!NO_VALUE_OPERATORS.has(c.op) && (
                    <ValueInputs condition={c} column={column} index={index} onChange={(changes) => update(c.key, changes)} />
                  )}
                  <IconButton
                    aria-label={`Remover condição ${index + 1}`}
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
              Adicionar condição
            </Button>
          </fieldset>
        </>
      )}

      {rule.query?.state === "erro" && !error && <FormError>Erro na busca atual: {rule.query.error}</FormError>}
      {error && <FormError>{error}</FormError>}

      <div className="flex flex-wrap items-center justify-end gap-2">
        {rule.query && (
          <Button
            variant="ghost"
            className="mr-auto text-danger"
            loading={remove.isPending}
            onClick={() =>
              remove.mutate(rule.id, {
                onSuccess: onClose,
                onError: (err) => setError(errorMessage(err)),
              })
            }
          >
            Remover busca
          </Button>
        )}
        <Button variant="ghost" onClick={onClose}>
          Cancelar
        </Button>
        <Button type="submit" variant="primary" loading={save.isPending}>
          Salvar e buscar
        </Button>
      </div>
    </form>
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
  const label = `Valor da condição ${index + 1}`;
  const listId = `query-values-${condition.key}`;
  if (column?.type === "boolean") {
    return (
      <Select aria-label={label} value={condition.value} onChange={(e) => onChange({ value: e.target.value })} className="w-32">
        <option value="">—</option>
        <option value="true">sim</option>
        <option value="false">não</option>
      </Select>
    );
  }
  if (LIST_OPERATORS.has(condition.op) && condition.op !== "between") {
    return (
      <Input
        aria-label={label}
        value={condition.value}
        onChange={(e) => onChange({ value: e.target.value })}
        placeholder="Valores separados por ;"
        title={column?.values.length ? `Valores da base: ${column.values.join("; ")}` : undefined}
        className="min-w-40 flex-1"
      />
    );
  }
  const type = (column && INPUT_TYPES[column.type]) ?? "text";
  const step = column?.type === "decimal" ? "any" : undefined;
  return (
    <div className={cn("flex min-w-40 flex-1 items-center gap-2")}>
      <Input
        aria-label={condition.op === "between" ? `${label} (mínimo)` : label}
        type={type}
        step={step}
        list={column?.values.length ? listId : undefined}
        value={condition.value}
        onChange={(e) => onChange({ value: e.target.value })}
      />
      {condition.op === "between" && (
        <>
          <span className="text-xs text-foreground-subtle">e</span>
          <Input
            aria-label={`${label} (máximo)`}
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
