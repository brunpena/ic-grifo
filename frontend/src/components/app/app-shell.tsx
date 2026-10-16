"use client";

import { CloudOff, RotateCcw } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { BrandLogo } from "@/components/brand-logo";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Spinner } from "@/components/ui/spinner";
import { errorMessage } from "@/lib/api";
import { useCurrentUser } from "@/lib/auth";
import { DESKTOP_QUERY, useMediaQuery } from "@/lib/use-media-query";
import { AppHeader } from "./app-header";
import { AppSidebar } from "./app-sidebar";

const SIDEBAR_KEY = "sidebar-collapsed";
/** Recolhida por padrão, como no lineFlow; a escolha da pessoa fica salva. */
function readCollapsed() {
  try {
    return typeof window === "undefined" || localStorage.getItem(SIDEBAR_KEY) !== "0";
  } catch {
    return true;
  }
}

/** Estrutura das telas logadas: sidebar, cabeçalho e conteúdo. Sem login, manda para /login. */
export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { data: user, isPending, error, refetch, isRefetching } = useCurrentUser();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);
  const isDesktop = useMediaQuery(DESKTOP_QUERY);

  useEffect(() => {
    if (!isPending && user === null) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [isPending, user, pathname, router]);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  if (error && !user) {
    return (
      <div className="flex min-h-dvh flex-1 items-center justify-center p-4">
        <EmptyState
          icon={CloudOff}
          title="Não foi possível conectar"
          description={errorMessage(error)}
          action={
            <Button size="sm" icon={<RotateCcw size={16} strokeWidth={1.75} aria-hidden />} loading={isRefetching} onClick={() => refetch()}>
              Tentar novamente
            </Button>
          }
        />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex min-h-dvh flex-1 flex-col items-center justify-center gap-4" aria-busy="true">
        <BrandLogo size={48} />
        <Spinner className="text-accent" />
        <span className="sr-only">Carregando</span>
      </div>
    );
  }

  const toggleSidebar = () => {
    if (isDesktop) {
      const next = !collapsed;
      setCollapsed(next);
      try {
        localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0");
      } catch {
        // Sem localStorage: a escolha vale só nesta sessão.
      }
    } else {
      setMobileOpen(true);
    }
  };

  return (
    <div className="flex h-dvh overflow-hidden">
      <AppSidebar user={user} collapsed={collapsed} className="max-lg:hidden" />

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div aria-hidden className="absolute inset-0 bg-brand-navy/60 animate-enter" onClick={() => setMobileOpen(false)} />
          <AppSidebar
            user={user}
            collapsed={false}
            onNavigate={() => setMobileOpen(false)}
            className="relative shadow-md animate-enter"
          />
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <AppHeader sidebarOpen={isDesktop ? !collapsed : mobileOpen} onToggleSidebar={toggleSidebar} />
        <main className="relative min-h-0 flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
