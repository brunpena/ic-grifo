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

const nextPath = () => safeNextPath(new URLSearchParams(window.location.search).get("next"));

export function LoginForm() {
  const router = useRouter();
  const { data: user } = useCurrentUser();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const emailId = useId();
  const passwordId = useId();

  // Quem já está logado vai direto para o sistema.
  useEffect(() => {
    if (user) router.replace(nextPath());
  }, [user, router]);

  return (
    <Card className="flex w-full flex-col gap-5 p-6">
      <div className="flex flex-col gap-1 text-center">
        <h1 className="text-xl font-semibold">Entrar</h1>
        <p className="text-[13px] text-foreground-muted">Acesse sua conta para validar documentos.</p>
      </div>

      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate({ email, password }, { onSuccess: () => router.replace(nextPath()) });
        }}
      >
        {login.error && <FormError>{errorMessage(login.error)}</FormError>}
        <Field label="E-mail" htmlFor={emailId}>
          <Input
            id={emailId}
            type="email"
            autoComplete="email"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="voce@empresa.com"
          />
        </Field>
        <Field label="Senha" htmlFor={passwordId}>
          <PasswordInput
            id={passwordId}
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <Button type="submit" variant="primary" loading={login.isPending} className="w-full">
          Entrar
        </Button>
      </form>

      <p className="text-center text-[13px] text-foreground-muted">
        Ainda não tem conta?{" "}
        <Link href="/cadastro" className="font-medium text-accent underline-offset-2 hover:underline">
          Criar conta
        </Link>
      </p>
    </Card>
  );
}
