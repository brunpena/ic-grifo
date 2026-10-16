import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { UiDemo } from "./ui-demo";

export const metadata: Metadata = { title: "Componentes · IC Grifo" };

// Vitrine dos componentes para revisão visual. Só existe em desenvolvimento.
export default function DevUiPage() {
  if (process.env.NODE_ENV !== "development") notFound();
  return <UiDemo />;
}
