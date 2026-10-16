"use client";

import { ChevronRight, LayoutGrid, LogOut, PanelLeft, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentProps, ReactNode } from "react";
import { ThemeToggle } from "@/components/theme-toggle";
import { IconButton } from "@/components/ui/icon-button";
import { cn } from "@/lib/utils";
import { navItemFor } from "./nav";
import { useSignOut } from "./use-sign-out";

type AppHeaderProps = {
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
};

export function AppHeader({ sidebarOpen, onToggleSidebar }: AppHeaderProps) {
  const pathname = usePathname();
  const current = navItemFor(pathname);
  const { signOut, pending } = useSignOut();

  return (
    <header className="relative z-20 flex h-14 shrink-0 items-center gap-2 bg-surface pr-3 pl-2 sm:pr-4 dark:bg-brand-navy">
      <IconButton
        aria-label={sidebarOpen ? "Recolher menu" : "Abrir menu"}
        aria-expanded={sidebarOpen}
        icon={<PanelLeft size={16} strokeWidth={1.75} aria-hidden />}
        tooltipSide="bottom"
        onClick={onToggleSidebar}
      />

      <nav aria-label="Você está em" className="flex min-w-0 items-center gap-1.5 text-[13px]">
        <Link
          href="/assistente"
          aria-label="Início"
          className="hidden size-8 items-center justify-center rounded-md text-foreground-muted transition-colors duration-150 ease-out hover:bg-surface-hover hover:text-foreground sm:inline-flex"
        >
          <LayoutGrid size={16} strokeWidth={1.75} aria-hidden />
        </Link>
        <ChevronRight size={14} strokeWidth={1.75} aria-hidden className="hidden shrink-0 text-foreground-subtle sm:block" />
        <span aria-current="page" className="truncate font-semibold text-foreground">
          {current?.title ?? "IC Grifo"}
        </span>
      </nav>

      <div className="ml-auto flex items-center gap-1.5">
        <HeaderLink href="/configuracoes" icon={<UserRound size={15} strokeWidth={1.75} aria-hidden />}>
          Minha conta
        </HeaderLink>
        <ThemeToggle className="border border-border bg-surface/60 dark:bg-white/[0.03]" />
        <HeaderButton icon={<LogOut size={15} strokeWidth={1.75} aria-hidden />} onClick={signOut} disabled={pending}>
          Sair
        </HeaderButton>
      </div>

      <HeaderCurve />
    </header>
  );
}

const HEADER_ACTION =
  "inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface/60 px-2.5 text-[13px] font-medium text-foreground-muted " +
  "transition-colors duration-150 ease-out hover:border-border-strong hover:bg-surface-hover hover:text-foreground disabled:opacity-50 dark:bg-white/[0.03]";

function HeaderLink({ href, icon, children }: { href: string; icon: ReactNode; children: ReactNode }) {
  return (
    <Link href={href} className={HEADER_ACTION}>
      {icon}
      <span className="max-md:sr-only">{children}</span>
    </Link>
  );
}

function HeaderButton({ icon, children, className, ...props }: ComponentProps<"button"> & { icon: ReactNode }) {
  return (
    <button type="button" className={cn(HEADER_ACTION, className)} {...props}>
      {icon}
      <span className="max-md:sr-only">{children}</span>
    </button>
  );
}

/**
 * Linha inferior do cabeçalho com uma curva suave à direita, que "abraça" as
 * ações. A forma é preenchida com a cor do cabeçalho e o traço é a borda.
 */
function HeaderCurve() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 1000 14"
      preserveAspectRatio="none"
      className="pointer-events-none absolute inset-x-0 top-full h-3.5 w-full"
    >
      <path d="M0 0 H520 C575 0 585 13 650 13 H1000 V0 Z" className="fill-surface dark:fill-brand-navy" />
      <path
        d="M0 0.5 H520 C575 0.5 585 13 650 13 H1000"
        fill="none"
        vectorEffect="non-scaling-stroke"
        className="stroke-border-strong"
        strokeWidth={1}
      />
    </svg>
  );
}
