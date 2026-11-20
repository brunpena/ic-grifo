"use client";

import { useSyncExternalStore } from "react";

const noop = () => () => {};

/**
 * `false` no servidor e enquanto o componente hidrata; `true` logo depois.
 *
 * Use antes de mostrar algo que só o navegador conhece (localStorage, cache do usuário,
 * idioma escolhido): o HTML pré-renderizado e a primeira renderização no cliente precisam
 * coincidir. O Next hidrata cada segmento (layout, página) separadamente, então um
 * `useEffect` no topo da árvore não garante que os segmentos abaixo já hidrataram.
 */
export function useHydrated() {
  return useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
}
