import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.services import llm


@pytest.fixture
def gemini(monkeypatch):
    """Troca o cliente HTTP do serviço por respostas da API do Gemini em sequência."""
    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr("chave-teste"))
    monkeypatch.setattr(llm.asyncio, "sleep", _no_sleep)
    responses: list[httpx.Response] = []
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return responses.pop(0)

    real = httpx.AsyncClient
    monkeypatch.setattr(
        llm.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    return responses, requests


async def _no_sleep(_seconds: float) -> None:
    return None


def _answer(text: str, finish: str = "STOP") -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}]}


async def test_extract_rules_parses_json_and_retries_rate_limit(gemini):
    responses, requests = gemini
    rules = {
        "rules": [
            {"type": "prazo", "excerpt": "em até 10 dias", "summary": " Prazo de 10 dias "},
            {"type": "inventado", "excerpt": "x", "summary": "y"},
        ]
    }
    responses += [
        httpx.Response(429, json={"error": {"details": [{"retryDelay": "3s"}]}}),
        httpx.Response(200, json=_answer(json.dumps(rules))),
    ]
    found = await llm.extract_rules_from_chunk(llm.TextChunk(0, "texto"))
    assert found == [llm.ExtractedRule("prazo", "em até 10 dias", "Prazo de 10 dias")]
    assert len(requests) == 2
    assert requests[-1].headers["x-goog-api-key"] == "chave-teste"
    assert requests[-1].url.path.endswith(":generateContent")


async def test_invalid_key_gives_friendly_message(gemini):
    responses, _ = gemini
    error = {"error": {"message": "API key not valid. Please pass a valid key."}}
    responses.append(httpx.Response(400, json=error))
    with pytest.raises(llm.LlmApiError, match="GEMINI_API_KEY"):
        await llm.extract_rules_from_chunk(llm.TextChunk(0, "texto"))


async def test_stream_chat_yields_text_and_maps_roles(gemini):
    responses, requests = gemini
    events = "".join(
        f"data: {json.dumps(_answer(part, finish))}\r\n\r\n"
        for part, finish in [("O prazo é ", None), ("10 dias [R1].", "STOP")]
    )
    responses.append(httpx.Response(200, text=events))
    history = [
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": "olá"},
        {"role": "user", "content": "qual o prazo?"},
    ]
    parts = [p async for p in llm.stream_chat("<documento/>", history)]
    assert "".join(parts) == "O prazo é 10 dias [R1]."
    body = json.loads(requests[0].content)
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert requests[0].url.params["alt"] == "sse"


async def test_missing_key_is_reported(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr(""))
    with pytest.raises(llm.LlmUnavailableError, match="GEMINI_API_KEY"):
        await llm.extract_rules("texto")
