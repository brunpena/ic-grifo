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

export type UploadProgress = { loaded: number; total: number };

/**
 * POST de um FormData com progresso do envio, que o fetch não informa. Resolve com o
 * JSON da resposta ou lança ApiError, como `unwrap`.
 */
export function postFormWithProgress<T>(
  path: `/api/v1/${string}`,
  form: FormData,
  onProgress: (progress: UploadProgress) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl(path));
    xhr.withCredentials = true;
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress({ loaded: e.loaded, total: e.total });
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as T);
      else reject(ApiError.fromBody(xhr.response, xhr.status));
    };
    xhr.onerror = () => reject(ApiError.network());
    xhr.send(form);
  });
}

/** URL absoluta de uma rota da API, para usos fora do cliente (ex.: pdf.js, downloads). */
export function apiUrl(path: `/api/v1/${string}`): string {
  return `${API_URL}${path}`;
}
