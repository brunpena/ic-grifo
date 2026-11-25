import { Gauge, Library, type LucideIcon, Settings, Sparkles } from "lucide-react";
import { msg, stripLocale } from "@/lib/i18n";

export type NavItem = {
  /** Caminho sem o idioma; os links completam com `useLocalePath()`. */
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
  { href: "/desempenho", label: msg("Desempenho"), title: msg("Desempenho do sistema"), icon: Gauge },
];

export const SETTINGS_NAV: NavItem = {
  href: "/configuracoes",
  label: msg("Configurações"),
  title: msg("Configurações"),
  icon: Settings,
};

/** Item do menu da página atual; aceita o caminho com ou sem o prefixo de idioma. */
export function navItemFor(pathname: string) {
  pathname = stripLocale(pathname);
  return [...MAIN_NAV, SETTINGS_NAV].find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`));
}
