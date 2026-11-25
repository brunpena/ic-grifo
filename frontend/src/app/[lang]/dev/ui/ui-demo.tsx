"use client";

import {
  Check,
  FileSearch,
  FileText,
  Plus,
  RotateCcw,
  Search,
  Trash2,
  TriangleAlert,
  Upload,
  X,
} from "lucide-react";
import { type ReactNode, useRef, useState } from "react";
import { BrandLogo } from "@/components/brand-logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { RuleStatusBadge, RuleTypeBadge, RuleTypeDot } from "@/components/ui/badge";
import { Button, type ButtonVariant } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { IconButton } from "@/components/ui/icon-button";
import { Input, Textarea } from "@/components/ui/input";
import { Popover } from "@/components/ui/popover";
import { ProgressBar } from "@/components/ui/progress-bar";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { Tooltip } from "@/components/ui/tooltip";
import { RULE_STATUS, RULE_TYPES, type RuleStatus, type RuleType } from "@/lib/design/tokens";
import { cn } from "@/lib/utils";
import { SystemDemo } from "./system-demo";

// Dados de exemplo: existem só nesta página.
const RULE_TYPE_KEYS = Object.keys(RULE_TYPES) as RuleType[];
const RULE_STATUS_KEYS = Object.keys(RULE_STATUS) as RuleStatus[];

// Estados que não dá para forçar com o mouse são simulados com as mesmas classes.
const FOCUS_SIM = "outline-2 outline-offset-2 outline-ring";
const FIELD_FOCUS_SIM = "border-ring ring-[3px] ring-accent-soft";
const HOVER_SIM: Record<ButtonVariant, string> = {
  primary: "bg-primary-hover",
  secondary: "bg-surface-hover",
  ghost: "bg-surface-hover",
  danger: "bg-danger/90",
};
const VARIANT_LABEL: Record<ButtonVariant, string> = {
  primary: "Primário",
  secondary: "Secundário",
  ghost: "Ghost",
  danger: "Perigo",
};

const icon = (Icon: typeof Check) => <Icon size={16} strokeWidth={1.75} aria-hidden />;

export function UiDemo() {
  return (
    <div className="flex flex-1 flex-col">
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-surface px-4 dark:bg-brand-navy">
        <BrandLogo size={28} labelled={false} />
        <span className="font-semibold">IC Grifo</span>
        <span className="text-xs text-foreground-subtle">/dev/ui</span>
        <ThemeToggle className="ml-auto" />
      </header>

      <main className="mx-auto flex w-full max-w-[1400px] flex-col gap-8 px-4 py-6">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold">Componentes</h1>
          <p className="text-[13px] text-foreground-muted">
            Os estados de hover e foco marcados como “simulado” usam as mesmas classes do estado real.
            Os componentes flutuantes abrem no tema da página (botão no canto superior direito).
          </p>
        </div>

        <Interactive />

        <div className="flex flex-col gap-1">
          <h2 className="text-xl font-semibold">Componentes do sistema</h2>
          <p className="text-[13px] text-foreground-muted">Com dados de exemplo, no tema da página.</p>
        </div>
        <SystemDemo />

        <h2 className="text-xl font-semibold">Componentes base nos dois temas</h2>

        <div className="grid gap-4 xl:grid-cols-2">
          <ThemePanel theme="light" title="Tema claro" />
          <ThemePanel theme="dark" title="Tema escuro" />
        </div>
      </main>
    </div>
  );
}

function ThemePanel({ theme, title }: { theme: "light" | "dark"; title: string }) {
  return (
    <section
      aria-label={title}
      className={cn(theme, "flex min-w-0 flex-col gap-6 rounded-lg border border-border bg-background p-4 text-foreground")}
    >
      <h2 className="text-xl font-semibold">{title}</h2>
      <BrandSection />
      <TypographySection />
      <ButtonsSection />
      <IconButtonsSection />
      <FieldsSection />
      <BadgesSection />
      <CardsSection />
      <FeedbackSection />
    </section>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold">{title}</h3>
      {children}
    </div>
  );
}

function State({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-1.5">
      <span className="text-xs text-foreground-subtle">{label}</span>
      {children}
    </div>
  );
}

function BrandSection() {
  return (
    <Section title="Marca e degradê">
      <div className="flex flex-wrap items-end gap-6">
        <State label="Logo 28 px">
          <BrandLogo size={28} />
        </State>
        <State label="Avatar 20 px">
          <BrandLogo size={20} />
        </State>
        <State label="Logo 72 px (brilho só no escuro)">
          <div className="relative">
            <div
              aria-hidden
              className="pointer-events-none absolute -inset-10 hidden rounded-full dark:block"
              style={{ background: "radial-gradient(closest-side, rgb(10 132 255 / 0.15), transparent)" }}
            />
            <BrandLogo size={72} className="relative" />
          </div>
        </State>
      </div>
      <p className="text-brand-gradient w-fit text-[32px] leading-tight font-bold">IC Grifo</p>
      <State label="Aba ativa no cabeçalho">
        <nav aria-label="Exemplo de navegação" className="flex h-10 gap-4">
          <span className="relative flex items-center text-sm font-medium text-foreground">
            Assistente
            <span aria-hidden className="bg-brand-gradient absolute inset-x-0 bottom-0 h-0.5 rounded-full" />
          </span>
          <span className="flex items-center text-sm font-medium text-foreground-muted">Base de regras</span>
        </nav>
      </State>
      <State label="Progresso de validação">
        <ProgressBar value={12} max={30} label="Regras validadas" className="w-64" />
      </State>
    </Section>
  );
}

function TypographySection() {
  return (
    <Section title="Tipografia">
      <div className="flex flex-col gap-1.5">
        <p className="text-xl font-semibold">Título de página · 20 px</p>
        <p className="text-sm font-semibold">Título de seção · 14 px</p>
        <p className="text-sm">Texto base · 14 px. O documento é o protagonista.</p>
        <p className="text-[13px] text-foreground-muted">Texto secundário · 13 px</p>
        <p className="text-xs text-foreground-subtle">Rótulo e metadado · 12 px</p>
        <p className="font-mono text-xs">“O contratado deverá entregar…” · p. 12 / 300</p>
        <p className="text-sm text-accent underline-offset-2 hover:underline">Link em accent</p>
      </div>
    </Section>
  );
}

function ButtonsSection() {
  const variants: ButtonVariant[] = ["primary", "secondary", "ghost", "danger"];
  return (
    <Section title="Button">
      <div className="flex flex-col gap-4 overflow-x-auto">
        {variants.map((variant) => (
          <div key={variant} className="flex flex-wrap items-end gap-3">
            <State label={VARIANT_LABEL[variant]}>
              <Button variant={variant} icon={icon(Plus)}>
                Criar regra
              </Button>
            </State>
            <State label="Hover (simulado)">
              <Button variant={variant} className={HOVER_SIM[variant]}>
                Hover
              </Button>
            </State>
            <State label="Foco (simulado)">
              <Button variant={variant} className={FOCUS_SIM}>
                Foco
              </Button>
            </State>
            <State label="Desabilitado">
              <Button variant={variant} disabled>
                Desabilitado
              </Button>
            </State>
            <State label="Carregando">
              <Button variant={variant} icon={icon(Upload)} loading>
                Enviando
              </Button>
            </State>
            <State label="Carregando sem ícone">
              <Button variant={variant} loading>
                Salvar
              </Button>
            </State>
          </div>
        ))}
        <div className="flex flex-wrap items-end gap-3">
          <State label="sm · 32 px">
            <Button size="sm" variant="primary" icon={icon(Plus)}>
              Criar regra
            </Button>
          </State>
          <State label="md · 36 px">
            <Button size="md" variant="primary" icon={icon(Plus)}>
              Criar regra
            </Button>
          </State>
        </div>
      </div>
    </Section>
  );
}

function IconButtonsSection() {
  return (
    <Section title="IconButton">
      <div className="flex flex-wrap items-end gap-4">
        <State label="Normal">
          <IconButton aria-label="Validar regra" icon={icon(Check)} />
        </State>
        <State label="Hover (simulado)">
          <IconButton aria-label="Rejeitar regra" icon={icon(X)} className="bg-surface-hover text-foreground" />
        </State>
        <State label="Foco (simulado)">
          <IconButton aria-label="Voltar para pendente" icon={icon(RotateCcw)} className={FOCUS_SIM} />
        </State>
        <State label="Desabilitado">
          <IconButton aria-label="Excluir" icon={icon(Trash2)} disabled />
        </State>
        <State label="Carregando">
          <IconButton aria-label="Validando" icon={icon(Check)} loading />
        </State>
        <State label="Secundário">
          <IconButton aria-label="Buscar" icon={icon(Search)} variant="secondary" />
        </State>
        <State label="Primário">
          <IconButton aria-label="Adicionar" icon={icon(Plus)} variant="primary" />
        </State>
      </div>
    </Section>
  );
}

function FieldsSection() {
  return (
    <Section title="Input, Textarea e Select">
      <div className="grid gap-3 sm:grid-cols-2">
        <State label="Vazio">
          <Input placeholder="Pergunte sobre as regras…" aria-label="Exemplo vazio" />
        </State>
        <State label="Preenchido">
          <Input defaultValue="prazo de entrega" aria-label="Exemplo preenchido" />
        </State>
        <State label="Foco (simulado)">
          <Input defaultValue="multa" aria-label="Exemplo com foco" className={FIELD_FOCUS_SIM} />
        </State>
        <State label="Desabilitado">
          <Input placeholder="Indisponível" aria-label="Exemplo desabilitado" disabled />
        </State>
        <State label="Erro">
          <Input defaultValue="abc" aria-label="Página" aria-invalid aria-describedby="demo-erro" />
          <span id="demo-erro" className="text-xs text-danger">
            Informe um número de página.
          </span>
        </State>
        <State label="Select">
          <Select aria-label="Tipo de regra" defaultValue="prazo">
            {RULE_TYPE_KEYS.map((t) => (
              <option key={t} value={t}>
                {RULE_TYPES[t].label}
              </option>
            ))}
          </Select>
        </State>
        <State label="Select desabilitado">
          <Select aria-label="Situação" disabled>
            <option>Pendente</option>
          </Select>
        </State>
        <State label="Textarea">
          <Textarea placeholder="Resumo da regra" aria-label="Resumo" />
        </State>
      </div>
    </Section>
  );
}

function BadgesSection() {
  return (
    <Section title="Badges">
      <div className="flex flex-wrap gap-2">
        {RULE_TYPE_KEYS.map((t) => (
          <RuleTypeBadge key={t} type={t} />
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {RULE_STATUS_KEYS.map((s) => (
          <RuleStatusBadge key={s} status={s} />
        ))}
      </div>
    </Section>
  );
}

function CardsSection() {
  return (
    <Section title="Card">
      <div className="grid gap-3 sm:grid-cols-2">
        <Card className="flex flex-col gap-1">
          <FileText size={20} strokeWidth={1.75} aria-hidden className="text-accent" />
          <p className="text-sm font-semibold">Assistente</p>
          <p className="text-[13px] text-foreground-muted">Envie um documento e valide as regras.</p>
        </Card>
        <Card className="flex flex-col gap-2">
          <p className="text-sm font-semibold">Resposta</p>
          <p className="text-[13px] text-foreground-muted">O prazo para recurso é de 5 dias úteis.</p>
          <div className="flex flex-wrap gap-1.5">
            <span className="inline-flex h-6 items-center gap-1.5 rounded-sm border border-border px-2 text-xs">
              <RuleTypeDot type="prazo" />
              Recurso em 5 dias úteis
            </span>
          </div>
        </Card>
      </div>
    </Section>
  );
}

function FeedbackSection() {
  return (
    <Section title="Carregamento, vazio e erro">
      <div className="grid gap-3 sm:grid-cols-2">
        <Card className="flex flex-col gap-2 p-3" aria-busy="true" aria-label="Carregando regras">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="flex h-11 items-center gap-3 border-b border-border last:border-0">
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-3 flex-1" />
              <Skeleton className="h-6 w-16" />
            </div>
          ))}
        </Card>
        <div className="flex justify-center rounded-lg bg-viewer p-4" aria-busy="true" aria-label="Carregando página">
          <Skeleton className="aspect-[210/297] w-40 rounded-none bg-white shadow-sm" />
        </div>
        <Card className="p-0">
          <EmptyState
            icon={FileSearch}
            title="Nenhuma regra encontrada"
            description="Ajuste os filtros ou selecione um trecho do documento para criar uma regra."
          />
        </Card>
        <Card className="p-0">
          <EmptyState
            icon={TriangleAlert}
            title="Não foi possível carregar"
            description="Verifique a conexão e tente de novo."
            action={
              <Button size="sm" icon={icon(RotateCcw)}>
                Tentar novamente
              </Button>
            }
          />
        </Card>
      </div>
      <div className="flex flex-col gap-2">
        {[
          [0, 30],
          [12, 30],
          [30, 30],
        ].map(([value, max]) => (
          <div key={value} className="flex items-center gap-3">
            <span className="w-44 text-[13px] text-foreground-muted tabular-nums">
              {value} de {max} regras validadas
            </span>
            <ProgressBar value={value} max={max} label="Regras validadas" className="flex-1" />
          </div>
        ))}
      </div>
    </Section>
  );
}

function Interactive() {
  const toast = useToast();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const popoverAnchor = useRef<HTMLButtonElement>(null);

  return (
    <Card className="flex flex-col gap-4">
      <h2 className="text-sm font-semibold">Componentes flutuantes (tema da página)</h2>
      <div className="flex flex-wrap items-center gap-3">
        <Tooltip content="O contratado deverá entregar o relatório em até 10 dias úteis após a assinatura.">
          <span tabIndex={0} className="max-w-56 truncate rounded-sm font-mono text-xs">
            O contratado deverá entregar o relatório em até 10 dias úteis após a assinatura.
          </span>
        </Tooltip>

        <Button
          ref={popoverAnchor}
          size="sm"
          variant="primary"
          icon={icon(Plus)}
          aria-expanded={popoverOpen}
          onClick={() => setPopoverOpen((v) => !v)}
        >
          Criar regra
        </Button>
        <Popover
          open={popoverOpen}
          onOpenChange={setPopoverOpen}
          anchorRef={popoverAnchor}
          label="Criar regra"
          className="w-72"
        >
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              setPopoverOpen(false);
              toast({ title: "Regra criada", variant: "success" });
            }}
          >
            <label className="flex flex-col gap-1 text-xs text-foreground-muted">
              Tipo
              <Select defaultValue="obrigacao">
                {RULE_TYPE_KEYS.map((t) => (
                  <option key={t} value={t}>
                    {RULE_TYPES[t].label}
                  </option>
                ))}
              </Select>
            </label>
            <label className="flex flex-col gap-1 text-xs text-foreground-muted">
              Resumo
              <Textarea rows={2} placeholder="Ex.: Entregar relatório em 10 dias" />
            </label>
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setPopoverOpen(false)}>
                Cancelar
              </Button>
              <Button size="sm" variant="primary" type="submit">
                Salvar
              </Button>
            </div>
          </form>
        </Popover>

        <Button size="sm" variant="danger" icon={icon(Trash2)} onClick={() => setDialogOpen(true)}>
          Excluir regra
        </Button>
        <Dialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          title="Excluir regra?"
          description="A regra e o grifo no documento serão removidos. Esta ação não pode ser desfeita."
          footer={
            <>
              <Button variant="secondary" onClick={() => setDialogOpen(false)}>
                Cancelar
              </Button>
              <Button
                variant="danger"
                loading={deleting}
                onClick={() => {
                  setDeleting(true);
                  window.setTimeout(() => {
                    setDeleting(false);
                    setDialogOpen(false);
                    toast({ title: "Regra excluída" });
                  }, 1200);
                }}
              >
                Excluir
              </Button>
            </>
          }
        />

        <Button size="sm" onClick={() => toast({ title: "Documento enviado", description: "Lendo as 300 páginas…" })}>
          Toast de informação
        </Button>
        <Button size="sm" onClick={() => toast({ title: "12 regras validadas", variant: "success" })}>
          Toast de sucesso
        </Button>
        <Button
          size="sm"
          onClick={() =>
            toast({ title: "Falha ao exportar", description: "Tente novamente em instantes.", variant: "error" })
          }
        >
          Toast de erro
        </Button>
      </div>
    </Card>
  );
}
