import { type NextRequest, NextResponse } from "next/server";
import { isLocale, type Locale, LOCALE_COOKIE, localeOfPath, localizePath } from "@/lib/i18n/core";

/**
 * Toda página fica sob o idioma (`/pt/...`, `/en/...`). Um link sem prefixo (ex.: um
 * favorito antigo de `/assistente`) vai para o idioma escolhido antes (cookie) ou, na
 * primeira visita, para o idioma do navegador.
 */
function preferredLocale(request: NextRequest): Locale {
  const saved = request.cookies.get(LOCALE_COOKIE)?.value;
  if (isLocale(saved)) return saved;
  const accepted = request.headers.get("accept-language") ?? "";
  // Primeiro idioma da lista que a interface tem; sem nenhum, português.
  for (const part of accepted.split(",")) {
    const tag = part.split(";")[0].trim().toLowerCase();
    if (tag.startsWith("pt")) return "pt";
    if (tag.startsWith("en")) return "en";
  }
  return "pt";
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (localeOfPath(pathname)) return;
  const url = request.nextUrl.clone();
  url.pathname = localizePath(preferredLocale(request), pathname);
  return NextResponse.redirect(url);
}

export const config = {
  // Fora: arquivos internos do Next, arquivos com extensão (ícones, imagens) e a imagem
  // de compartilhamento gerada em `app/opengraph-image.tsx`.
  matcher: ["/((?!_next/|api/|opengraph-image|.*\\.[\\w]+$).*)"],
};
