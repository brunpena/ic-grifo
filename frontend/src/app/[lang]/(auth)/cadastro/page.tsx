import { msg } from "@/lib/i18n/core";
import { localizedMetadata } from "@/lib/i18n/metadata";
import { RegisterForm } from "@/components/auth/register-form";

export const generateMetadata = () => localizedMetadata(msg("Criar conta"));

export default function Page() {
  return <RegisterForm />;
}
