import createClient from "openapi-fetch";
import { ApiError } from "./errors";
import type { paths } from "./schema";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);

/**
 * Cliente tipado gerado a partir do OpenAPI. As rotas já incluem o prefixo `/api/v1`,
 * por isso a base é só a URL do servidor.
 */
// `credentials: "include"` envia o cookie de sessão (login) nas chamadas à API.
export const api = createClient<paths>({ baseUrl: API_URL, credentials: "include" });

// Falhas de rede (servidor fora do ar, CORS, offline) viram ApiError com mensagem em português.
api.use({
  onError() {
    return ApiError.network();
  },
});

type Result<T> = { data?: T; error?: unknown; response: Response };

/**
 * Desembrulha a resposta do openapi-fetch: devolve `data` ou lança ApiError.
 * Pensado para ser usado direto como `queryFn`/`mutationFn` do TanStack Query.
 */
export async function unwrap<T>(request: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await request;
  if (!response.ok || error !== undefined) throw ApiError.fromBody(error, response.status);
  return data as T;
}

/** URL absoluta de uma rota da API, para usos fora do cliente (ex.: pdf.js, downloads). */
export function apiUrl(path: `/api/v1/${string}`): string {
  return `${API_URL}${path}`;
}
