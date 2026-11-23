"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, FormError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { errorMessage } from "@/lib/api";
import { safeNextPath, useCurrentUser, useLogin } from "@/lib/auth";
import { useLocalePath, useT } from "@/lib/i18n";

/** Para onde ir depois do login (sem idioma; o chamador completa com o idioma atual). */
const nextPath = () => safeNextPath(new URLSearchParams(window.location.search).get("next"));

export function LoginForm() {
  const router = useRouter();
  // `dataUpdatedAt` 0 = cópia guardada no navegador, ainda não conferida pela API.
  const { data: user, dataUpdatedAt } = useCurrentUser();
  const confirmed = !!user && dataUpdatedAt > 0;
  const login = useLogin();
  const t = useT();
  const href = useLocalePath();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const emailId = useId();
  const passwordId = useId();

  // Quem já está logado vai direto para o sistema.
  useEffect(() => {
    if (confirmed) router.replace(href(nextPath()));
  }, [confirmed, router, href]);

  return (
    <Card className="flex w-full flex-col gap-5 p-6">
      <div className="flex flex-col gap-1 text-center">
        <h1 className="text-xl font-semibold">{t("Entrar")}</h1>
        <p className="text-[13px] text-foreground-muted">{t("Acesse sua conta para validar documentos.")}</p>
      </div>

      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate({ email, password }, { onSuccess: () => router.replace(href(nextPath())) });
        }}
      >
        {login.error && <FormError>{errorMessage(login.error, t)}</FormError>}
        <Field label={t("E-mail")} htmlFor={emailId}>
          <Input
            id={emailId}
            type="email"
            autoComplete="email"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("voce@empresa.com")}
          />
        </Field>
        <Field label={t("Senha")} htmlFor={passwordId}>
          <PasswordInput
            id={passwordId}
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <Button type="submit" variant="primary" loading={login.isPending} className="w-full">
          {t("Entrar")}
        </Button>
      </form>

      <p className="text-center text-[13px] text-foreground-muted">
        {t("Ainda não tem conta?")}{" "}
        <Link href={href("/cadastro")} className="font-medium text-accent underline-offset-2 hover:underline">
          {t("Criar conta")}
        </Link>
      </p>
    </Card>
  );
}
