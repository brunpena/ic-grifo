/** Formato documentado de todos os erros do back: `{ error: { code, message } }`. */
type ErrorBody = { error: { code: string; message: string } };

const NETWORK_MESSAGE =
  "Não foi possível conectar ao servidor. Verifique sua conexão e se a API está no ar.";

/** Erro da API com a mensagem em português, pronta para exibir. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }

  static network(): ApiError {
    return new ApiError("network_error", NETWORK_MESSAGE, 0);
  }

  /** Constrói o erro a partir do corpo já lido (ou de qualquer coisa que veio no lugar dele). */
  static fromBody(body: unknown, status: number): ApiError {
    if (isErrorBody(body)) return new ApiError(body.error.code, body.error.message, status);
    return new ApiError("http_error", `Erro inesperado do servidor (código ${status}).`, status);
  }

  static async fromResponse(response: Response): Promise<ApiError> {
    const body: unknown = await response.json().catch(() => null);
    return ApiError.fromBody(body, response.status);
  }
}

function isErrorBody(value: unknown): value is ErrorBody {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const error = (value as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
}

/** Mensagem amigável para qualquer erro capturado na interface. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Algo deu errado. Tente novamente.";
}
