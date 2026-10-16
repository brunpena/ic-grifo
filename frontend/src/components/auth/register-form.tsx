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

const PASSWORD_HINT = "Pelo menos 8 caracteres.";

export function RegisterForm() {
  const router = useRouter();
  const { data: user } = useCurrentUser();
  const register = useRegister();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const nameId = useId();
  const emailId = useId();
  const passwordId = useId();

  useEffect(() => {
    if (user) router.replace("/assistente");
  }, [user, router]);

  return (
    <Card className="flex w-full flex-col gap-5 p-6">
      <div className="flex flex-col gap-1 text-center">
        <h1 className="text-xl font-semibold">Criar conta</h1>
        <p className="text-[13px] text-foreground-muted">Comece a validar regras em poucos minutos.</p>
      </div>

      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (password.length < 8) {
            setPasswordError("A senha precisa ter pelo menos 8 caracteres.");
            return;
          }
          setPasswordError(null);
          register.mutate({ name, email, password }, { onSuccess: () => router.replace("/assistente") });
        }}
      >
        {register.error && <FormError>{errorMessage(register.error)}</FormError>}
        <Field label="Nome" htmlFor={nameId}>
          <Input id={nameId} autoComplete="name" required autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="E-mail" htmlFor={emailId}>
          <Input
            id={emailId}
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="voce@empresa.com"
          />
        </Field>
        <Field label="Senha" htmlFor={passwordId} hint={PASSWORD_HINT} error={passwordError}>
          <PasswordInput
            id={passwordId}
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={passwordError ? true : undefined}
            aria-describedby={fieldDescribedBy(passwordId, { hint: PASSWORD_HINT, error: passwordError })}
          />
        </Field>
        <Button type="submit" variant="primary" loading={register.isPending} className="w-full">
          Criar conta
        </Button>
      </form>

      <p className="text-center text-[13px] text-foreground-muted">
        Já tem conta?{" "}
        <Link href="/login" className="font-medium text-accent underline-offset-2 hover:underline">
          Entrar
        </Link>
      </p>
    </Card>
  );
}
