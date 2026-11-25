import { msg } from "@/lib/i18n/core";
import { localizedMetadata } from "@/lib/i18n/metadata";
import { notFound } from "next/navigation";
import { UiDemo } from "./ui-demo";

export const generateMetadata = () => localizedMetadata(msg("Componentes"));

// Vitrine dos componentes para revisão visual. Só existe em desenvolvimento.
export default function DevUiPage() {
  if (process.env.NODE_ENV !== "development") notFound();
  return <UiDemo />;
}
