from typing import Any

import orjson
from starlette.responses import JSONResponse


def dumps(content: Any) -> str:
    return orjson.dumps(content, default=str).decode()


class OrjsonResponse(JSONResponse):
    """Resposta JSON serializada com orjson (usada em erros e respostas sem response_model)."""

    def render(self, content: Any) -> bytes:
        return orjson.dumps(content, default=str)
