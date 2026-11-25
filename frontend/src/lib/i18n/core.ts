import { en } from "./en";

/**
 * Parte do i18n sem React: usada pelo servidor (metadados, proxy) e pelos hooks de
 * `./index.ts`. Ver a explicação completa lá.
 */

export type Locale = "pt" | "en";
export const LOCALES: Locale[] = ["pt", "en"];
export const DEFAULT_LOCALE: Locale = "pt";

/** Cookie lido pelo `proxy.ts` para escolher o idioma de um link sem prefixo. */
export const LOCALE_COOKIE = "grifo-locale";

export const isLocale = (value: unknown): value is Locale => value === "pt" || value === "en";

export const htmlLang = (locale: Locale) => (locale === "en" ? "en" : "pt-BR");
/** Locale do Intl (números e datas). */
export const intlLocale = (locale: Locale) => (locale === "en" ? "en-US" : "pt-BR");

/** Idioma no começo de um caminho (`/en/regras` → "en"), ou `null` se não houver. */
export function localeOfPath(pathname: string): Locale | null {
  const first = pathname.split("/")[1];
  return isLocale(first) ? first : null;
}

/** Caminho sem o prefixo de idioma (`/en/regras` → `/regras`; `/en` → `/`). */
export function stripLocale(pathname: string): string {
  return localeOfPath(pathname) ? pathname.slice(3) || "/" : pathname;
}

/** Caminho interno no idioma pedido (`/regras` → `/en/regras`). Troca um prefixo existente. */
export function localizePath(locale: Locale, path: string): string {
  const bare = stripLocale(path);
  return bare === "/" ? `/${locale}` : `/${locale}${bare}`;
}

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

/**
 * Marca um texto de uma constante fora dos componentes (rótulos, menus) para tradução.
 * Não traduz nada: o componente traduz na hora de exibir, com `t(valor)`.
 */
export const msg = (text: string) => text;

/** Título da aba no idioma da rota: `pageTitle("en", "Regras")` → "Rules · IC Grifo". */
export function pageTitle(locale: Locale, title: string) {
  return `${translator(locale)(title)} · IC Grifo`;
}

/** Idioma de um parâmetro de rota já validado pelo layout (`notFound` para os demais). */
export const routeLocale = (lang: string): Locale => (isLocale(lang) ? lang : DEFAULT_LOCALE);
