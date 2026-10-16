from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(description="Código estável do erro, para tratamento no front.")
    message: str = Field(description="Mensagem legível, em português.")


class ErrorResponse(BaseModel):
    """Formato de todas as respostas de erro da API."""

    error: ErrorDetail


def error_responses(*codes: int) -> dict[int | str, dict]:
    """Documenta no OpenAPI os códigos de erro que uma rota pode devolver."""
    return {code: {"model": ErrorResponse} for code in codes}
