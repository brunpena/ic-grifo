"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, fieldDescribedBy, FormError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { errorMessage } from "@/lib/api";
import { useCurrentUser, useRegister } from "@/lib/auth";
import { useT } from "@/lib/i18n";

export function RegisterForm() {
  const router = useRouter();
  // `dataUpdatedAt` 0 = cópia guardada no navegador, ainda não conferida pela API.
  const { data: user, dataUpdatedAt } = useCurrentUser();
  const confirmed = !!user && dataUpdatedAt > 0;
  const register = useRegister();
  const t = useT();
  const passwordHint = t("Pelo menos 8 caracteres.");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const nameId = useId();
  const emailId = useId();
  const passwordId = useId();

  useEffect(() => {
    if (confirmed) router.replace("/assistente");
  }, [confirmed, router]);

  return (
    <Card className="flex w-full flex-col gap-5 p-6">
      <div className="flex flex-col gap-1 text-center">
        <h1 className="text-xl font-semibold">{t("Criar conta")}</h1>
        <p className="text-[13px] text-foreground-muted">{t("Comece a validar regras em poucos minutos.")}</p>
      </div>

      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (password.length < 8) {
            setPasswordError(t("A senha precisa ter pelo menos 8 caracteres."));
            return;
          }
          setPasswordError(null);
          register.mutate({ name, email, password }, { onSuccess: () => router.replace("/assistente") });
        }}
      >
        {register.error && <FormError>{errorMessage(register.error, t)}</FormError>}
        <Field label={t("Nome")} htmlFor={nameId}>
          <Input id={nameId} autoComplete="name" required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label={t("E-mail")} htmlFor={emailId}>
          <Input
            id={emailId}
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("voce@empresa.com")}
          />
        </Field>
        <Field label={t("Senha")} htmlFor={passwordId} hint={passwordHint} error={passwordError}>
          <PasswordInput
            id={passwordId}
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={passwordError ? true : undefined}
            aria-describedby={fieldDescribedBy(passwordId, { hint: passwordHint, error: passwordError })}
          />
        </Field>
        <Button type="submit" variant="primary" loading={register.isPending} className="w-full">
          {t("Criar conta")}
        </Button>
      </form>

      <p className="text-center text-[13px] text-foreground-muted">
        {t("Já tem conta?")}{" "}
        <Link href="/login" className="font-medium text-accent underline-offset-2 hover:underline">
          {t("Entrar")}
        </Link>
      </p>
    </Card>
  );
}
