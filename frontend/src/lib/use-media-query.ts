"use client";

import { useSyncExternalStore } from "react";

export const DESKTOP_QUERY = "(min-width: 1024px)";

/** Acompanha uma media query. No servidor, devolve `serverValue`. */
export function useMediaQuery(query: string, serverValue = true) {
  return useSyncExternalStore(
    (onChange) => {
      const media = window.matchMedia(query);
      media.addEventListener("change", onChange);
      return () => media.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => serverValue,
  );
}
