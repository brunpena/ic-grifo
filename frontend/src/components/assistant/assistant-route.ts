"use client";

import { useParams, usePathname, useRouter } from "next/navigation";
import { type RefObject, useEffect, useRef, useState } from "react";
import { closeAnalysis } from "@/lib/analyses";
import { isSwitchingLocale, useLocalePath } from "@/lib/i18n";

export type AssistantRoute = { analysisId: string | null; documentId: string | null };

/** Caminho (sem idioma) de cada etapa do Assistente. */
export function assistantPath({ analysisId, documentId }: AssistantRoute) {
  if (documentId) return `/assistente/documentos/${documentId}`;
  if (analysisId) return `/assistente/analises/${analysisId}`;
  return "/assistente";
}

/**
 * Análise e documento abertos, lidos da URL (`/assistente/analises/{id}` e
 * `/assistente/documentos/{id}`). `navigate` empilha a nova etapa no histórico do
 * navegador, então Voltar/Avançar percorrem as etapas.
 *
 * Até a URL mudar de fato (a navegação é uma transição), a tela já usa o destino: sem
 * isso, ela piscaria a etapa anterior entre o clique e a troca de endereço.
 */
export function useAssistantRoute() {
  const params = useParams<{ analysisId?: string; documentId?: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const href = useLocalePath();
  const [pending, setPending] = useState<{ from: string; route: AssistantRoute } | null>(null);
  // A URL mudou (pela navegação pedida ou por Voltar/Avançar): vale a URL.
  if (pending && pending.from !== pathname) setPending(null);

  const route: AssistantRoute = pending?.route ?? {
    analysisId: params.analysisId ?? null,
    documentId: params.documentId ?? null,
  };

  const navigate = (next: AssistantRoute, { replace = false }: { replace?: boolean } = {}) => {
    const target = href(assistantPath(next));
    if (target === pathname) return;
    setPending({ from: pathname, route: next });
    if (replace) router.replace(target, { scroll: false });
    else router.push(target, { scroll: false });
  };

  return { ...route, navigate };
}

/**
 * Mantém a análise aberta no servidor enquanto ela está em uso e a encerra (para o
 * processamento e libera os caches DuckDB) quando outra análise entra no lugar, ao sair do
 * Assistente ou ao fechar a aba. Voltar para a tela inicial não encerra: a pessoa pode
 * avançar de novo para a mesma análise.
 *
 * Devolve as análises já encerradas, para um envio que termina depois do encerramento
 * pedir o encerramento de novo.
 */
export function useAnalysisLifecycle(analysisId: string | null): RefObject<Set<string>> {
  const closed = useRef(new Set<string>());
  const active = useRef<string | null>(null);
  const mounted = useRef(false);

  const release = (id: string) => {
    if (closed.current.has(id)) return;
    closed.current.add(id);
    // `keepalive`: entrega mesmo se a página estiver sendo fechada.
    void closeAnalysis(id, true).catch(() => {
      // O navegador pode interromper a rede durante o encerramento da aba.
    });
  };

  useEffect(() => {
    if (!analysisId) return;
    const previous = active.current;
    if (previous && previous !== analysisId) release(previous);
    active.current = analysisId;
    closed.current.delete(analysisId);
  }, [analysisId]);

  useEffect(() => {
    mounted.current = true;
    const onPageHide = () => {
      // Trocar de idioma recarrega a página no mesmo endereço: a análise continua.
      if (active.current && !isSwitchingLocale()) release(active.current);
    };
    window.addEventListener("pagehide", onPageHide);
    return () => {
      mounted.current = false;
      window.removeEventListener("pagehide", onPageHide);
      // Espera um instante: no modo estrito do React a tela é montada de novo na hora,
      // e isso não é sair do Assistente.
      setTimeout(() => {
        if (!mounted.current && active.current) release(active.current);
      }, 0);
    };
  }, []);

  return closed;
}
