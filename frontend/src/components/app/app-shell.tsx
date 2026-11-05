"use client";

import { CloudOff, RotateCcw } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { BrandLogo } from "@/components/brand-logo";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { useCurrentUser } from "@/lib/auth";
import { DESKTOP_QUERY, useMediaQuery } from "@/lib/use-media-query";
import { cn } from "@/lib/utils";
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

  if (!user) return <ShellSkeleton collapsed={collapsed} />;

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

/** Mesma estrutura da tela logada (menu, cabeçalho e conteúdo) enquanto a sessão é conferida. */
function ShellSkeleton({ collapsed }: { collapsed: boolean }) {
  return (
    <div role="status" aria-busy className="flex h-dvh overflow-hidden">
      <span className="sr-only">Carregando</span>
      <aside
        aria-hidden
        className={cn(
          "flex h-full shrink-0 flex-col gap-2 border-r border-border bg-surface px-3 max-lg:hidden dark:bg-brand-navy",
          collapsed ? "w-[60px] items-center" : "w-60",
        )}
      >
        <div className="flex h-14 items-center gap-2.5">
          <BrandLogo size={28} />
          {!collapsed && <Skeleton className="h-3 w-24" />}
        </div>
        {[1, 2, 3].map((n) => (
          <Skeleton key={n} className={cn("h-9", collapsed ? "w-9" : "w-full")} />
        ))}
        <div className="mt-auto flex items-center gap-2.5 py-3">
          <Skeleton className="size-8 shrink-0 rounded-full" />
          {!collapsed && <Skeleton className="h-3 flex-1" />}
        </div>
      </aside>
      <div aria-hidden className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-14 shrink-0 items-center gap-3 bg-surface px-3 dark:bg-brand-navy">
          <Skeleton className="size-8" />
          <Skeleton className="h-3 w-40" />
          <Skeleton className="ml-auto size-8 rounded-full" />
        </div>
        <div className="flex flex-1 items-start justify-center overflow-hidden px-4 py-10">
          <div className="flex w-full max-w-2xl flex-col gap-6">
            <Skeleton className="mx-auto h-7 w-2/3" />
            <Skeleton className="mx-auto h-3 w-1/2" />
            <Skeleton className="h-36 w-full rounded-xl" />
            <Skeleton className="h-24 w-full rounded-xl" />
          </div>
        </div>
      </div>
    </div>
  );
}
