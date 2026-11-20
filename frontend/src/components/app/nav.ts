import { Library, type LucideIcon, Settings, Sparkles } from "lucide-react";
import { msg } from "@/lib/i18n";

export type NavItem = {
  href: string;
  /** Textos em português; traduza ao exibir com `t(...)`. */
  label: string;
  /** Título no cabeçalho (breadcrumb). */
  title: string;
  icon: LucideIcon;
};

export const MAIN_NAV: NavItem[] = [
  { href: "/assistente", label: msg("Assistente"), title: msg("Assistente de IA"), icon: Sparkles },
  { href: "/regras", label: msg("Base de regras"), title: msg("Base de regras"), icon: Library },
];

export const SETTINGS_NAV: NavItem = {
  href: "/configuracoes",
  label: msg("Configurações"),
  title: msg("Configurações"),
  icon: Settings,
};

export function navItemFor(pathname: string) {
  return [...MAIN_NAV, SETTINGS_NAV].find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`));
}
