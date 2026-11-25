import { msg } from "@/lib/i18n/core";
import { localizedMetadata } from "@/lib/i18n/metadata";
import { LoginForm } from "@/components/auth/login-form";

export const generateMetadata = () => localizedMetadata(msg("Entrar"));

export default function Page() {
  return <LoginForm />;
}
