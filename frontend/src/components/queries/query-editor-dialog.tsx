"use client";

import type { FormEvent } from "react";
import { QueryBuilder, useQueryBuilder } from "@/components/queries/query-builder";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { FormError } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import type { Dataset } from "@/lib/analyses";
import { errorMessage } from "@/lib/api";
import type { Rule } from "@/lib/documents";
import { useT } from "@/lib/i18n";
import { type StructuredQuery, useDeleteRuleQuery, useSetRuleQuery } from "@/lib/queries";

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
  const t = useT();
  return (
    <Dialog
      open={!!rule}
      onOpenChange={(open) => !open && onClose()}
      title={t("Busca da regra")}
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
  const t = useT();
  const builder = useQueryBuilder(initialQuery(rule, datasets), datasets);
  const save = useSetRuleQuery(documentId);
  const remove = useDeleteRuleQuery(documentId);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const query = builder.build();
    if (!query) return;
    save.mutate(
      { ruleId: rule.id, query },
      {
        onSuccess: () => {
          toast({
            title: t("Busca salva"),
            description: t("Selecione a regra para consultar os registros na tabela."),
            variant: "success",
          });
          onClose();
        },
        onError: (err) => builder.setError(errorMessage(err, t)),
      },
    );
  };

  if (!datasets.length) {
    return (
      <p className="text-[13px] text-foreground-muted">
        {t("Esta análise não tem bases de dados. Envie um CSV para transformar a regra em busca.")}
      </p>
    );
  }

  return (
    <form onSubmit={submit} className="flex min-w-0 flex-col gap-4">
      <blockquote className="max-h-24 overflow-auto border-l-2 border-accent pl-3 text-[13px] text-foreground-muted">
        {rule.excerpt}
      </blockquote>

      {rule.category === "geral" && !rule.query && (
        <p className="text-xs text-foreground-muted">
          {t("Esta regra foi registrada como geral (não verificável no CSV). Ao salvar uma busca, ela passa para as regras verificáveis.")}
        </p>
      )}

      <QueryBuilder state={builder} datasets={datasets} />

      {rule.query?.state === "erro" && !builder.error && <FormError>{t("Erro na busca atual: {error}", { error: t(rule.query.error ?? "") })}</FormError>}
      {builder.error && <FormError>{builder.error}</FormError>}

      <div className="flex flex-wrap items-center justify-end gap-2">
        {rule.query && (
          <Button
            variant="ghost"
            className="mr-auto text-danger"
            loading={remove.isPending}
            onClick={() =>
              remove.mutate(rule.id, {
                onSuccess: onClose,
                onError: (err) => builder.setError(errorMessage(err, t)),
              })
            }
          >
            {t("Remover busca")}
          </Button>
        )}
        <Button variant="ghost" onClick={onClose}>
          {t("Cancelar")}
        </Button>
        <Button type="submit" variant="primary" loading={save.isPending}>
          {t("Salvar e buscar")}
        </Button>
      </div>
    </form>
  );
}
