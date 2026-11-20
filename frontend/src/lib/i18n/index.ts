import { useSyncExternalStore } from "react";
import { en } from "./en";

/**
 * Tradução da interface (português e inglês), no estilo gettext: o próprio texto em
 * português é a chave. `t("Sair")` devolve "Sair" ou "Sign out"; um texto sem tradução
 * aparece em português em vez de quebrar a tela. `npm run i18n:check` lista as chaves
 * usadas em `t(...)`/`plural(...)` que ainda não estão em `en.ts`.
 *
 * Variáveis entram com chaves: `t("Olá, {name}", { name })`. A mesma chave precisa
 * existir, com as mesmas variáveis, em `en.ts`.
 */

export type Locale = "pt" | "en";
export const LOCALES: Locale[] = ["pt", "en"];

const STORAGE_KEY = "grifo:locale";
const listeners = new Set<() => void>();
let current: Locale | null = null;

function detect(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "pt" || stored === "en") return stored;
  } catch {
    // Sem localStorage: segue o idioma do navegador.
  }
  return navigator.language?.toLowerCase().startsWith("pt") ? "pt" : "en";
}

function getSnapshot(): Locale {
  current ??= detect();
  return current;
}

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  // Outra aba trocou o idioma.
  const onStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY) return;
    current = detect();
    onChange();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}

export function setLocale(locale: Locale) {
  current = locale;
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // Sem localStorage: vale até recarregar a página.
  }
  document.documentElement.lang = htmlLang(locale);
  for (const listener of listeners) listener();
}

/**
 * Idioma atual. No servidor e durante a hidratação vale português (o HTML pré-renderizado
 * está em português); o idioma salvo entra logo em seguida, sem divergência de HTML.
 */
export function useLocale(): Locale {
  return useSyncExternalStore(subscribe, getSnapshot, () => "pt");
}

export const htmlLang = (locale: Locale) => (locale === "en" ? "en" : "pt-BR");
/** Locale do Intl (números e datas). */
export const intlLocale = (locale: Locale) => (locale === "en" ? "en-US" : "pt-BR");

type Vars = Record<string, string | number>;

export type Translate = {
  (text: string, vars?: Vars): string;
  /** Escolhe singular/plural pelo número `n` (também disponível como `{n}`). */
  plural: (n: number, one: string, other: string, vars?: Vars) => string;
  locale: Locale;
  /** Formata um número no padrão do idioma. */
  number: (n: number, options?: Intl.NumberFormatOptions) => string;
};

const fill = (text: string, vars?: Vars) =>
  vars ? text.replace(/\{(\w+)\}/g, (match, key: string) => (key in vars ? String(vars[key]) : match)) : text;

const cache = new Map<Locale, Translate>();

export function translator(locale: Locale): Translate {
  const cached = cache.get(locale);
  if (cached) return cached;
  const intl = intlLocale(locale);
  const t = ((text: string, vars?: Vars) => fill(locale === "en" ? (en[text] ?? text) : text, vars)) as Translate;
  t.plural = (n, one, other, vars) => t(n === 1 ? one : other, { n: t.number(n), ...vars });
  t.locale = locale;
  t.number = (n, options) => n.toLocaleString(intl, options);
  cache.set(locale, t);
  return t;
}

/** Função de tradução do idioma atual; o componente renderiza de novo ao trocar o idioma. */
export function useT(): Translate {
  return translator(useLocale());
}

/**
 * Marca um texto de uma constante fora dos componentes (rótulos, menus) para tradução.
 * Não traduz nada: o componente traduz na hora de exibir, com `t(valor)`.
 */
export const msg = (text: string) => text;

/**
 * Tradução no idioma atual para código fora de componentes (ex.: mensagens de erro).
 * Não faz o componente renderizar de novo ao trocar o idioma; quem exibe o texto
 * normalmente já usa `useT()` e renderiza de novo.
 */
export function currentTranslator(): Translate {
  return translator(typeof window === "undefined" ? "pt" : getSnapshot());
}
