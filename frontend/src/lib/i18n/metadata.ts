import type { Metadata } from "next";
import { lang } from "next/root-params";
import { pageTitle, routeLocale } from "./core";

/**
 * Metadados de uma página com o título traduzido no idioma da rota. O idioma vem do
 * parâmetro raiz `[lang]` (`next/root-params`), conhecido já no build.
 *
 *     export const generateMetadata = () => localizedMetadata(msg("Base de regras"));
 */
export async function localizedMetadata(title: string): Promise<Metadata> {
  return { title: pageTitle(routeLocale((await lang()) ?? ""), title) };
}
