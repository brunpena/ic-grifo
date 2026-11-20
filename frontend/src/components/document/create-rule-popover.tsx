"use client";

import { Plus } from "lucide-react";
import { type RefObject, useId, useState } from "react";
import { useT } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Popover } from "@/components/ui/popover";
import { RuleTypeSelect } from "@/components/ui/rule-type-select";
import type { RuleType } from "@/lib/design/tokens";
import type { FloatingAnchor } from "@/lib/floating";

type CreateRulePopoverProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** A seleção de texto (`Range`) ou o elemento sobre o qual o botão aparece. */
  anchorRef: RefObject<FloatingAnchor | null>;
  onCreate: (rule: { type: RuleType; summary: string }) => void;
  creating?: boolean;
};

/**
 * Aparece logo acima da seleção de texto como um botão "Criar regra". Ao clicar,
 * o mesmo popover vira o formulário (tipo e resumo).
 */
export function CreateRulePopover({ open, onOpenChange, anchorRef, onCreate, creating }: CreateRulePopoverProps) {
  const t = useT();
  const [expanded, setExpanded] = useState(false);
  const [type, setType] = useState<RuleType>("obrigacao");
  const [summary, setSummary] = useState("");
  const typeLabelId = useId();
  const summaryId = useId();

  const change = (next: boolean) => {
    if (!next) {
      setExpanded(false);
      setSummary("");
    }
    onOpenChange(next);
  };

  if (!expanded) {
    return (
      <Popover
        open={open}
        onOpenChange={change}
        anchorRef={anchorRef}
        label={t("Criar regra a partir da seleção")}
        placement="top"
        initialFocus={false}
        className="border-none bg-transparent p-0"
      >
        <Button
          size="sm"
          variant="primary"
          icon={<Plus size={16} strokeWidth={1.75} aria-hidden />}
          // Mantém a seleção de texto ao clicar.
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => setExpanded(true)}
        >
          {t("Criar regra")}
        </Button>
      </Popover>
    );
  }

  return (
    <Popover
      open={open}
      onOpenChange={change}
      anchorRef={anchorRef}
      label={t("Criar regra")}
      placement="top"
      className="w-72"
    >
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          onCreate({ type, summary: summary.trim() });
        }}
      >
        <div className="flex flex-col gap-1">
          <span id={typeLabelId} className="text-xs font-medium text-foreground-muted">
            {t("Tipo")}
          </span>
          <RuleTypeSelect value={type} onChange={setType} aria-labelledby={typeLabelId} autoFocus />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={summaryId} className="text-xs font-medium text-foreground-muted">
            {t("Resumo")}
          </label>
          <Textarea
            id={summaryId}
            rows={2}
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder={t("Ex.: Entregar o relatório em até 10 dias úteis")}
            required
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={() => change(false)}>
            {t("Cancelar")}
          </Button>
          <Button size="sm" variant="primary" type="submit" loading={creating} disabled={!summary.trim()}>
            {t("Criar regra")}
          </Button>
        </div>
      </form>
    </Popover>
  );
}
