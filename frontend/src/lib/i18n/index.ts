import { useRouter } from "next/navigation";
import { useContext } from "react";
import {
  DEFAULT_LOCALE,
  type Locale,
  LOCALE_COOKIE,
  localeOfPath,
  localizePath,
  translator,
  type Translate,
} from "./core";
import { LocaleContext } from "./locale-provider";

/**
 * Tradução da interface (português e inglês), no estilo gettext: o próprio texto em
 * português é a chave. `t("Sair")` devolve "Sair" ou "Sign out"; um texto sem tradução
 * aparece em português em vez de quebrar a tela. `npm run i18n:check` lista as chaves
 * usadas em `t(...)`/`plural(...)` que ainda não estão em `en.ts`.
 *
 * Variáveis entram com chaves: `t("Olá, {name}", { name })`. A mesma chave precisa
 * existir, com as mesmas variáveis, em `en.ts`.
 *
 * O idioma faz parte da URL (`/pt/assistente`, `/en/assistente`): é o segmento `[lang]`
 * de `src/app/[lang]`. Assim o servidor já renderiza no idioma certo, cada idioma tem o
 * seu link, e trocar de idioma é só navegar para o mesmo caminho com outro prefixo.
 * Links sem prefixo são redirecionados pelo `src/proxy.ts` (cookie ou navegador).
 */

export {
  DEFAULT_LOCALE,
  htmlLang,
  intlLocale,
  isLocale,
  LOCALES,
  localeOfPath,
  localizePath,
  msg,
  stripLocale,
  translator,
} from "./core";
export type { Locale, Translate } from "./core";

/** Idioma da rota atual (o segmento `[lang]` da URL, entregue pelo layout raiz). */
export function useLocale(): Locale {
  return useContext(LocaleContext);
}

/** Função de tradução do idioma atual; o componente renderiza de novo ao trocar o idioma. */
export function useT(): Translate {
  return translator(useLocale());
}

/** Guarda a escolha para o proxy usar em links sem idioma (ex.: `/assistente`). */
export function rememberLocale(locale: Locale) {
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=31536000; samesite=lax`;
}

/**
 * Troca o idioma: vai para o mesmo caminho (e query) com o outro prefixo. Usa `replace`
 * para o botão Voltar do navegador não ficar alternando entre idiomas.
 */
export function useSetLocale() {
  const router = useRouter();
  return (locale: Locale) => {
    rememberLocale(locale);
    // Lido no clique (não com `usePathname`), para não tornar dinâmica a página inteira.
    const { pathname } = window.location;
    if (localeOfPath(pathname) === locale) return;
    switchingUntil = Date.now() + 5000;
    router.replace(localizePath(locale, pathname) + window.location.search, { scroll: false });
  };
}

let switchingUntil = 0;

/**
 * Verdadeiro logo depois de trocar o idioma. Mudar o prefixo da URL troca o layout raiz,
 * e o Next recarrega a página: quem limpa recursos ao fechar a aba (`pagehide`) pode
 * ignorar essa recarga, já que a mesma tela volta no outro idioma.
 */
export const isSwitchingLocale = () => Date.now() < switchingUntil;

/** Monta caminhos internos no idioma atual: `href("/regras")` → `/en/regras`. */
export function useLocalePath() {
  const locale = useLocale();
  return (path: string) => localizePath(locale, path);
}

/**
 * Tradução no idioma atual para código fora de componentes (ex.: mensagens de erro).
 * Lê o idioma da URL; não faz o componente renderizar de novo ao trocar o idioma (quem
 * exibe o texto normalmente já usa `useT()`).
 */
export function currentTranslator(): Translate {
  if (typeof window === "undefined") return translator(DEFAULT_LOCALE);
  return translator(localeOfPath(window.location.pathname) ?? DEFAULT_LOCALE);
}
