import { Circle, CircleCheck, CircleX } from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { msg, useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export const PROCESSING_STEPS = [msg("Enviando"), msg("Lendo o documento"), msg("Pronto para grifar")];

type ProcessingStepsProps = {
  /** Índice da etapa atual. Ao chegar na última ("Pronto"), tudo aparece concluído. */
  current: number;
  /** A etapa atual falhou. */
  failed?: boolean;
  /** Textos em português; traduzidos ao exibir. */
  steps?: readonly string[];
  className?: string;
};

export function ProcessingSteps({ current, failed, steps = PROCESSING_STEPS, className }: ProcessingStepsProps) {
  const t = useT();
  const last = steps.length - 1;
  return (
    <ol className={cn("flex flex-col gap-3", className)}>
      {steps.map((label, i) => {
        const done = i < current || (i === last && current >= last && !failed);
        const isCurrent = i === current && !done;
        const state = done ? t("concluída") : isCurrent ? (failed ? t("com erro") : t("em andamento")) : t("a seguir");
        return (
          <li
            key={label}
            aria-current={isCurrent ? "step" : undefined}
            className={cn(
              "flex items-center gap-2.5 text-sm",
              done || isCurrent ? "text-foreground" : "text-foreground-subtle",
              isCurrent && "font-medium",
            )}
          >
            {done ? (
              <CircleCheck size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-success" />
            ) : isCurrent && failed ? (
              <CircleX size={16} strokeWidth={1.75} aria-hidden className="shrink-0 text-danger" />
            ) : isCurrent ? (
              <Spinner className="text-accent" />
            ) : (
              <Circle size={16} strokeWidth={1.75} aria-hidden className="shrink-0" />
            )}
            {t(label)}
            <span className="sr-only">({state})</span>
          </li>
        );
      })}
    </ol>
  );
}
