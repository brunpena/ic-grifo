import { Library, type LucideIcon, Settings, Sparkles } from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  /** Título no cabeçalho (breadcrumb). */
  title: string;
  icon: LucideIcon;
};

export const MAIN_NAV: NavItem[] = [
  { href: "/assistente", label: "Assistente", title: "Assistente de IA", icon: Sparkles },
  { href: "/regras", label: "Base de regras", title: "Base de regras", icon: Library },
];

export const SETTINGS_NAV: NavItem = {
  href: "/configuracoes",
  label: "Configurações",
  title: "Configurações",
  icon: Settings,
};

export function navItemFor(pathname: string) {
  return [...MAIN_NAV, SETTINGS_NAV].find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`));
}
