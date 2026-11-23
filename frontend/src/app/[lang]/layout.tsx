import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import { notFound } from "next/navigation";
import { htmlLang, isLocale, LOCALES, routeLocale, translator } from "@/lib/i18n/core";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { THEME_INIT_SCRIPT } from "@/lib/theme";
import { Providers } from "./providers";
import "../globals.css";

// Mesmo valor de `API_URL` (lib/api/client), sem trazer o cliente para o servidor.
const API_ORIGIN = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

// Cada idioma é pré-renderizado; outros valores em `[lang]` dão 404 (ver o layout).
export function generateStaticParams() {
  return LOCALES.map((lang) => ({ lang }));
}

export async function generateMetadata({ params }: LayoutProps<"/[lang]">): Promise<Metadata> {
  const locale = routeLocale((await params).lang);
  const t = translator(locale);
  return {
    title: "IC Grifo",
    description: t(
      "Encontre e valide as regras de contratos, editais e regulamentos, cada uma ligada ao trecho exato de onde veio.",
    ),
    // Liga as versões do mesmo endereço em cada idioma (buscadores e leitores).
    alternates: { languages: Object.fromEntries(LOCALES.map((l) => [htmlLang(l), `/${l}`])) },
  };
}

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#030a1f" },
  ],
};

export default async function RootLayout({ children, params }: LayoutProps<"/[lang]">) {
  const { lang } = await params;
  if (!isLocale(lang)) notFound();
  return (
    // O script do <head> pode adicionar a classe `dark` antes da hidratação.
    <html
      lang={htmlLang(lang)}
      className={`${GeistSans.variable} ${GeistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        {/* Abre a conexão (DNS, TCP e TLS) com a API enquanto o JavaScript ainda carrega:
            a primeira consulta (`/auth/me`) já encontra o caminho pronto. */}
        <link rel="preconnect" href={API_ORIGIN} crossOrigin="use-credentials" />
      </head>
      <body className="flex min-h-full flex-col">
        <LocaleProvider locale={lang}>
          <Providers>{children}</Providers>
        </LocaleProvider>
      </body>
    </html>
  );
}
