"use client";

import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, unwrap, type User } from "@/lib/api";
import { stripLocale } from "@/lib/i18n";

export const ME_QUERY_KEY = ["auth", "me"] as const;

/**
 * Último usuário logado neste navegador. Ao abrir a página, o menu e o cabeçalho aparecem
 * na hora com ele, enquanto `/auth/me` confere a sessão em segundo plano; se ela tiver
 * expirado, a resposta 401 apaga esta cópia e o AppShell manda para o login.
 */
const USER_STORAGE_KEY = "grifo:user";

function readStoredUser(): User | undefined {
  try {
    const stored = localStorage.getItem(USER_STORAGE_KEY);
    const parsed: unknown = stored ? JSON.parse(stored) : undefined;
    return parsed && typeof parsed === "object" && "id" in parsed && "name" in parsed ? (parsed as User) : undefined;
  } catch {
    return undefined; // Sem localStorage ou valor corrompido: espera a API.
  }
}

function storeUser(user: User | null) {
  try {
    if (user) localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
    else localStorage.removeItem(USER_STORAGE_KEY);
  } catch {
    // Sem localStorage: a próxima abertura só espera a API.
  }
}

/** Usuário da sessão atual; `null` quando não há login. */
export function useCurrentUser() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: async (): Promise<User | null> => {
      try {
        const user = await unwrap(api.GET("/api/v1/auth/me"));
        storeUser(user);
        return user;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          storeUser(null);
          return null;
        }
        throw error;
      }
    },
    staleTime: 5 * 60_000,
  });
}

/**
 * Coloca o último usuário no cache logo depois da hidratação (não antes: o HTML
 * pré-renderizado tem o skeleton, e os dois precisam coincidir). Fica marcado como antigo,
 * então `/auth/me` continua conferindo a sessão; a resposta substitui esta cópia.
 */
export function seedStoredUser(queryClient: QueryClient) {
  if (queryClient.getQueryData(ME_QUERY_KEY) !== undefined) return;
  const stored = readStoredUser();
  if (stored) queryClient.setQueryData(ME_QUERY_KEY, stored, { updatedAt: 0 });
}

function useSetCurrentUser() {
  const queryClient = useQueryClient();
  return (user: User) => {
    storeUser(user);
    queryClient.setQueryData(ME_QUERY_KEY, user);
  };
}

export function useLogin() {
  const setUser = useSetCurrentUser();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      unwrap(api.POST("/api/v1/auth/login", { body })),
    onSuccess: setUser,
  });
}

export function useRegister() {
  const setUser = useSetCurrentUser();
  return useMutation({
    mutationFn: (body: { name: string; email: string; password: string }) =>
      unwrap(api.POST("/api/v1/auth/register", { body })),
    onSuccess: setUser,
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/auth/logout")),
    // Mesmo se a API falhar, a interface sai da conta; os dados em cache são descartados.
    onSettled: () => {
      storeUser(null);
      queryClient.clear();
      queryClient.setQueryData(ME_QUERY_KEY, null);
    },
  });
}

export function useUpdateProfile() {
  const setUser = useSetCurrentUser();
  return useMutation({
    mutationFn: (body: { name?: string; email?: string; job_title?: string | null; organization?: string | null }) =>
      unwrap(api.PATCH("/api/v1/me", { body })),
    onSuccess: setUser,
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      unwrap(api.POST("/api/v1/me/password", { body })),
  });
}

/**
 * Só aceita caminhos internos, para o `?next=` do login não virar um redirecionamento
 * aberto. Devolve o caminho sem idioma: quem navega completa com o idioma atual.
 */
export function safeNextPath(value: string | null, fallback = "/assistente") {
  return value && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/\\") ? stripLocale(value) : fallback;
}

export function firstName(name: string) {
  return name.trim().split(/\s+/)[0] ?? name;
}

export function initials(name: string) {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")).toUpperCase();
}
