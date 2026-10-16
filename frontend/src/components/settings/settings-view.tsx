"use client";

import { LogOut, Monitor, Moon, Sun } from "lucide-react";
import { type ChangeEvent, type ReactNode, useId, useState } from "react";
import { ApiStatus } from "@/components/api-status";
import { useSignOut } from "@/components/app/use-sign-out";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, fieldDescribedBy, FormError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { useToast } from "@/components/ui/toast";
import { errorMessage, type User } from "@/lib/api";
import { useChangePassword, useCurrentUser, useUpdateProfile } from "@/lib/auth";
import { applyTheme, clearStoredTheme, readStoredTheme, storeTheme, systemTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

export function SettingsView() {
  const { data: user } = useCurrentUser();
  if (!user) return null;
  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 pt-8 pb-12 sm:px-6">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold">Configurações</h1>
          <p className="text-[13px] text-foreground-muted">Seu perfil, sua senha e a aparência do sistema.</p>
        </div>
        {/* A chave remonta o formulário quando os dados salvos mudam. */}
        <ProfileSection key={user.created_at + user.email + user.name} user={user} />
        <PasswordSection />
        <AppearanceSection />
        <SessionSection />
      </div>
    </div>
  );
}

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <Card className="flex flex-col gap-5 p-5 sm:p-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-sm font-semibold">{title}</h2>
        <p className="text-[13px] text-foreground-muted">{description}</p>
      </div>
      {children}
    </Card>
  );
}

function ProfileSection({ user }: { user: User }) {
  const toast = useToast();
  const update = useUpdateProfile();
  const [form, setForm] = useState({
    name: user.name,
    email: user.email,
    job_title: user.job_title ?? "",
    organization: user.organization ?? "",
  });
  const ids = { name: useId(), email: useId(), job: useId(), org: useId() };
  const set = (field: keyof typeof form) => (e: ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [field]: e.target.value }));
  const dirty =
    form.name !== user.name ||
    form.email !== user.email ||
    form.job_title !== (user.job_title ?? "") ||
    form.organization !== (user.organization ?? "");

  return (
    <Section title="Perfil" description="Como você aparece no sistema.">
      <div className="flex items-center gap-4">
        <Avatar name={form.name || user.name} size={56} />
        <div className="flex min-w-0 flex-col">
          <span className="truncate font-semibold">{user.name}</span>
          <span className="truncate text-[13px] text-foreground-muted">{user.email}</span>
          <span className="text-xs text-foreground-subtle">
            Conta criada em {new Date(user.created_at).toLocaleDateString("pt-BR")}
          </span>
        </div>
      </div>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          update.mutate(
            {
              name: form.name,
              email: form.email,
              job_title: form.job_title,
              organization: form.organization,
            },
            { onSuccess: () => toast({ title: "Perfil atualizado", variant: "success" }) },
          );
        }}
      >
        {update.error && <FormError>{errorMessage(update.error)}</FormError>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nome" htmlFor={ids.name}>
            <Input id={ids.name} autoComplete="name" required value={form.name} onChange={set("name")} />
          </Field>
          <Field label="E-mail" htmlFor={ids.email}>
            <Input id={ids.email} type="email" autoComplete="email" required value={form.email} onChange={set("email")} />
          </Field>
          <Field label="Cargo" htmlFor={ids.job}>
            <Input
              id={ids.job}
              autoComplete="organization-title"
              placeholder="Ex.: Analista de contratos"
              value={form.job_title}
              onChange={set("job_title")}
            />
          </Field>
          <Field label="Organização" htmlFor={ids.org}>
            <Input
              id={ids.org}
              autoComplete="organization"
              placeholder="Ex.: Secretaria de Compras"
              value={form.organization}
              onChange={set("organization")}
            />
          </Field>
        </div>
        <div className="flex justify-end">
          <Button type="submit" variant="primary" loading={update.isPending} disabled={!dirty}>
            Salvar alterações
          </Button>
        </div>
      </form>
    </Section>
  );
}

function PasswordSection() {
  const toast = useToast();
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const ids = { current: useId(), next: useId(), confirm: useId() };
  const hint = "Pelo menos 8 caracteres. As outras sessões abertas serão encerradas.";

  return (
    <Section title="Senha" description="Troque a senha usada para entrar.">
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (next.length < 8) return setLocalError("A nova senha precisa ter pelo menos 8 caracteres.");
          if (next !== confirm) return setLocalError("A confirmação não confere com a nova senha.");
          setLocalError(null);
          change.mutate(
            { current_password: current, new_password: next },
            {
              onSuccess: () => {
                setCurrent("");
                setNext("");
                setConfirm("");
                toast({ title: "Senha alterada", variant: "success" });
              },
            },
          );
        }}
      >
        {(localError || change.error) && <FormError>{localError ?? errorMessage(change.error)}</FormError>}
        <Field label="Senha atual" htmlFor={ids.current} className="sm:max-w-[calc(50%-8px)]">
          <PasswordInput
            id={ids.current}
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nova senha" htmlFor={ids.next} hint={hint}>
            <PasswordInput
              id={ids.next}
              autoComplete="new-password"
              required
              value={next}
              onChange={(e) => setNext(e.target.value)}
              aria-describedby={fieldDescribedBy(ids.next, { hint })}
            />
          </Field>
          <Field label="Confirmar nova senha" htmlFor={ids.confirm}>
            <PasswordInput
              id={ids.confirm}
              autoComplete="new-password"
              required
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </Field>
        </div>
        <div className="flex justify-end">
          <Button type="submit" loading={change.isPending} disabled={!current || !next || !confirm}>
            Alterar senha
          </Button>
        </div>
      </form>
    </Section>
  );
}

type ThemeChoice = "system" | "light" | "dark";

const THEME_OPTIONS: { value: ThemeChoice; label: string; icon: ReactNode }[] = [
  { value: "system", label: "Sistema", icon: <Monitor size={16} strokeWidth={1.75} aria-hidden /> },
  { value: "light", label: "Claro", icon: <Sun size={16} strokeWidth={1.75} aria-hidden /> },
  { value: "dark", label: "Escuro", icon: <Moon size={16} strokeWidth={1.75} aria-hidden /> },
];

function AppearanceSection() {
  // Esta tela só renderiza no navegador (depois do login), então o localStorage já existe.
  const [choice, setChoice] = useState<ThemeChoice>(() => readStoredTheme() ?? "system");
  const name = useId();

  const pick = (value: ThemeChoice) => {
    setChoice(value);
    if (value === "system") {
      clearStoredTheme();
      applyTheme(systemTheme());
    } else {
      storeTheme(value);
      applyTheme(value);
    }
  };

  return (
    <Section title="Aparência" description="O tema também pode ser trocado pelo botão do cabeçalho.">
      <div role="radiogroup" aria-label="Tema" className="grid grid-cols-3 gap-2 sm:max-w-md">
        {THEME_OPTIONS.map((option) => (
          <label
            key={option.value}
            className={cn(
              "flex h-10 cursor-pointer items-center justify-center gap-2 rounded-md border border-border text-[13px] font-medium text-foreground-muted",
              "transition-colors duration-150 ease-out hover:bg-surface-hover has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring",
              choice === option.value && "border-accent bg-accent-soft text-foreground hover:bg-accent-soft",
            )}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={choice === option.value}
              onChange={() => pick(option.value)}
              className="sr-only"
            />
            {option.icon}
            {option.label}
          </label>
        ))}
      </div>
    </Section>
  );
}

function SessionSection() {
  const { signOut, pending } = useSignOut();
  return (
    <Section title="Sessão" description="Encerre o acesso neste navegador.">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ApiStatus />
        <Button variant="danger" icon={<LogOut size={16} strokeWidth={1.75} aria-hidden />} loading={pending} onClick={signOut}>
          Sair da conta
        </Button>
      </div>
    </Section>
  );
}
