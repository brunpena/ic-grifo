"use client";

import { useState } from "react";

function read<T>(key: string, fallback: T, parse: (value: unknown) => T | null): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    return parse(JSON.parse(raw)) ?? fallback;
  } catch {
    // Sem localStorage (modo privado, bloqueio) ou valor corrompido: volta ao padrão.
    return fallback;
  }
}

/**
 * Estado salvo no localStorage entre recarregamentos. `parse` valida o que veio do
 * armazenamento (devolva null para descartar). Só use em telas que aparecem depois de
 * uma interação: no servidor vale sempre o `fallback`.
 */
export function usePersistentState<T>(key: string, fallback: T, parse: (value: unknown) => T | null) {
  const [value, setValue] = useState<T>(() => read(key, fallback, parse));
  const update = (next: T | ((current: T) => T)) => {
    setValue((current) => {
      const resolved = typeof next === "function" ? (next as (current: T) => T)(current) : next;
      try {
        localStorage.setItem(key, JSON.stringify(resolved));
      } catch {
        // Sem localStorage: a escolha vale só nesta sessão.
      }
      return resolved;
    });
  };
  return [value, update] as const;
}

/** Armazenamento para o `useDefaultLayout` dos painéis, tolerante a localStorage bloqueado. */
export const safeLayoutStorage = {
  getItem(key: string) {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  setItem(key: string, value: string) {
    try {
      localStorage.setItem(key, value);
    } catch {
      // Sem localStorage: as larguras valem só nesta sessão.
    }
  },
};
