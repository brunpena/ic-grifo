"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useSyncExternalStore } from "react";
import { applyTheme, readStoredTheme, storeTheme } from "@/lib/theme";
import { IconButton } from "./ui/icon-button";

const SYSTEM_DARK = "(prefers-color-scheme: dark)";

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
}

const isDarkNow = () => document.documentElement.classList.contains("dark");

/** Alterna entre claro e escuro. Sem escolha salva, segue o sistema. */
export function ThemeToggle({ className }: { className?: string }) {
  // No servidor o tema é desconhecido; o valor real chega logo após a hidratação.
  const isDark = useSyncExternalStore(subscribe, isDarkNow, () => false);

  // Enquanto a pessoa não escolher, acompanha mudanças do tema do sistema.
  useEffect(() => {
    const media = window.matchMedia(SYSTEM_DARK);
    const onSystemChange = () => {
      if (!readStoredTheme()) applyTheme(media.matches ? "dark" : "light");
    };
    media.addEventListener("change", onSystemChange);
    return () => media.removeEventListener("change", onSystemChange);
  }, []);

  const label = isDark ? "Usar tema claro" : "Usar tema escuro";

  return (
    <IconButton
      aria-label={label}
      tooltipSide="bottom"
      className={className}
      onClick={() => {
        const next = isDark ? "light" : "dark";
        storeTheme(next);
        applyTheme(next);
      }}
      icon={
        isDark ? (
          <Sun size={16} strokeWidth={1.75} aria-hidden />
        ) : (
          <Moon size={16} strokeWidth={1.75} aria-hidden />
        )
      }
    />
  );
}
