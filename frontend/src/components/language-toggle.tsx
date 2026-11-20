"use client";

import { useEffect } from "react";
import { htmlLang, type Locale, LOCALES, setLocale, useLocale, useT } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const NAMES: Record<Locale, string> = { pt: "Português", en: "English" };

/**
 * Bandeiras para trocar o idioma da interface. Em SVG porque o Windows não desenha
 * bandeiras em emoji (mostra só as letras "BR"/"US").
 */
export function LanguageToggle({ className }: { className?: string }) {
  const locale = useLocale();
  const t = useT();

  // Mantém o `lang` do <html> (leitores de tela, hifenização) no idioma exibido.
  useEffect(() => {
    document.documentElement.lang = htmlLang(locale);
  }, [locale]);

  return (
    <div
      role="group"
      aria-label={t("Idioma")}
      className={cn("inline-flex h-8 items-center gap-0.5 rounded-md border border-border bg-surface/60 p-0.5 dark:bg-white/[0.03]", className)}
    >
      {LOCALES.map((option) => {
        const active = option === locale;
        return (
          <button
            key={option}
            type="button"
            lang={htmlLang(option)}
            aria-pressed={active}
            aria-label={NAMES[option]}
            title={NAMES[option]}
            onClick={() => setLocale(option)}
            className={cn(
              "inline-flex h-full items-center justify-center rounded-sm px-1.5 transition duration-150 ease-out",
              active ? "bg-surface shadow-sm" : "opacity-55 grayscale-[40%] hover:opacity-100 hover:grayscale-0",
            )}
          >
            {option === "pt" ? <BrazilFlag /> : <UsFlag />}
          </button>
        );
      })}
    </div>
  );
}

const FLAG = "h-3.5 w-5 shrink-0 overflow-hidden rounded-[2px] ring-1 ring-black/10 dark:ring-white/15";

function BrazilFlag() {
  return (
    <svg viewBox="0 0 20 14" aria-hidden className={FLAG}>
      <rect width="20" height="14" fill="#009c3b" />
      <path d="M10 1.6 18.2 7 10 12.4 1.8 7Z" fill="#ffdf00" />
      <circle cx="10" cy="7" r="3.1" fill="#002776" />
      <path d="M7.05 6.25q3-.85 5.9.75" stroke="#fff" strokeWidth=".55" fill="none" />
    </svg>
  );
}

function UsFlag() {
  return (
    <svg viewBox="0 0 20 14" aria-hidden className={FLAG}>
      <rect width="20" height="14" fill="#fff" />
      {[0, 2, 4, 6, 8, 10, 12].map((i) => (
        <rect key={i} y={(i * 14) / 13} width="20" height={14 / 13} fill="#b22234" />
      ))}
      <rect width="8.6" height={(7 * 14) / 13} fill="#3c3b6e" />
      {[1.4, 3.6, 5.8].flatMap((y, row) =>
        (row % 2 ? [2.2, 4.3, 6.4] : [1.15, 3.25, 5.35, 7.45]).map((x) => (
          <circle key={`${x}-${y}`} cx={x} cy={y} r=".42" fill="#fff" />
        )),
      )}
    </svg>
  );
}
