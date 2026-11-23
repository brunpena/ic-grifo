"use client";

import { createContext, type ReactNode } from "react";
import { DEFAULT_LOCALE, type Locale } from "./core";

/**
 * Idioma da rota, entregue pelo layout raiz (`app/[lang]/layout.tsx`), que já o conhece
 * no build. Ler de `useParams()` tornaria dinâmica toda página com id na URL (o Next só
 * sabe os ids na hora do pedido) e impediria a pré-renderização das telas.
 */
export const LocaleContext = createContext<Locale>(DEFAULT_LOCALE);

export function LocaleProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  return <LocaleContext value={locale}>{children}</LocaleContext>;
}
