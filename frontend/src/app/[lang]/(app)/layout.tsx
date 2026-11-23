import { Suspense } from "react";
import { AppShell, ShellSkeleton } from "@/components/app/app-shell";

export default function AppLayout({ children }: LayoutProps<"/[lang]">) {
  // A estrutura lê a URL (menu ativo, retorno do login); nas páginas com id (documento,
  // análise) a URL só existe no pedido, então o HTML pré-renderizado mostra o skeleton.
  return (
    <Suspense fallback={<ShellSkeleton collapsed />}>
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
