"use client";

import { LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandLogo } from "@/components/brand-logo";
import { Avatar } from "@/components/ui/avatar";
import { Tooltip } from "@/components/ui/tooltip";
import type { User } from "@/lib/api";
import { cn } from "@/lib/utils";
import { MAIN_NAV, type NavItem, SETTINGS_NAV } from "./nav";
import { useSignOut } from "./use-sign-out";

type AppSidebarProps = {
  user: User;
  collapsed: boolean;
  /** Chamado ao navegar (fecha a gaveta no celular). */
  onNavigate?: () => void;
  className?: string;
};

export function AppSidebar({ user, collapsed, onNavigate, className }: AppSidebarProps) {
  const pathname = usePathname();
  const { signOut, pending } = useSignOut();
  const isActive = (item: NavItem) => pathname === item.href || pathname.startsWith(`${item.href}/`);

  return (
    <aside
      aria-label="Menu"
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-150 ease-out dark:bg-brand-navy",
        collapsed ? "w-[60px]" : "w-60",
        className,
      )}
    >
      <Link
        href="/assistente"
        onClick={onNavigate}
        className={cn("flex h-14 shrink-0 items-center gap-2.5 rounded-md px-3.5", collapsed && "justify-center px-0")}
      >
        <BrandLogo size={30} labelled={collapsed} priority />
        {!collapsed && <span className="font-semibold tracking-tight">IC Grifo</span>}
      </Link>

      <nav aria-label="Principal" className="flex flex-col gap-1 px-2.5 pt-3">
        {MAIN_NAV.map((item) => (
          <SidebarLink key={item.href} item={item} active={isActive(item)} collapsed={collapsed} onNavigate={onNavigate} />
        ))}
      </nav>

      <div className="mt-auto flex flex-col gap-1 border-t border-border p-2.5">
        <SidebarLink item={SETTINGS_NAV} active={isActive(SETTINGS_NAV)} collapsed={collapsed} onNavigate={onNavigate} />
        <SidebarAction collapsed={collapsed} label="Sair" icon={LogOut} onClick={signOut} disabled={pending} />
        <Link
          href="/configuracoes"
          onClick={onNavigate}
          className={cn(
            "mt-1 flex items-center gap-2.5 rounded-md p-1.5 transition-colors duration-150 ease-out hover:bg-surface-hover",
            collapsed && "justify-center",
          )}
        >
          <Avatar name={user.name} size={30} />
          {collapsed ? (
            <span className="sr-only">Minha conta: {user.name}</span>
          ) : (
            <span className="flex min-w-0 flex-col">
              <span className="truncate text-[13px] font-medium">{user.name}</span>
              <span className="truncate text-xs text-foreground-subtle">{user.email}</span>
            </span>
          )}
        </Link>
      </div>
    </aside>
  );
}

const ITEM =
  "relative flex h-9 items-center gap-3 rounded-md px-2.5 text-[13px] font-medium text-foreground-muted transition-colors duration-150 ease-out hover:bg-surface-hover hover:text-foreground";

function SidebarLink({
  item,
  active,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  const link = (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(ITEM, collapsed && "w-9 justify-center px-0", active && "bg-accent-soft text-foreground hover:bg-accent-soft")}
    >
      {/* Indicador do item ativo, no degradê da marca. */}
      {active && <span aria-hidden className="bg-brand-gradient absolute top-2 bottom-2 -left-2.5 w-0.5 rounded-full" />}
      <Icon size={16} strokeWidth={1.75} aria-hidden className={cn("shrink-0", active && "text-accent")} />
      <span className={cn(collapsed && "sr-only")}>{item.label}</span>
    </Link>
  );
  return collapsed ? (
    <Tooltip content={item.label} side="right">
      {link}
    </Tooltip>
  ) : (
    link
  );
}

function SidebarAction({
  label,
  icon: Icon,
  collapsed,
  onClick,
  disabled,
}: {
  label: string;
  icon: NavItem["icon"];
  collapsed: boolean;
  onClick: () => void;
  disabled?: boolean;
}) {
  const button = (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(ITEM, "disabled:opacity-50", collapsed && "w-9 justify-center px-0")}
    >
      <Icon size={16} strokeWidth={1.75} aria-hidden className="shrink-0" />
      <span className={cn(collapsed && "sr-only")}>{label}</span>
    </button>
  );
  return collapsed ? (
    <Tooltip content={label} side="right">
      {button}
    </Tooltip>
  ) : (
    button
  );
}
