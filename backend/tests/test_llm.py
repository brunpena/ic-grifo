import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.services import llm


@pytest.fixture(autouse=True)
def reset_key_pool(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key_2", SecretStr(""))
    monkeypatch.setattr(get_settings(), "gemini_api_key_3", SecretStr(""))
    monkeypatch.setattr(llm, "_key_cooldowns", {})
    monkeypatch.setattr(llm, "_key_cursor", 0)


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
    text = "Objeto. Pagar em até 10 dias; caso atrase, multa. Fim."
    sentences = llm.split_sentences(text)
    rules = {
        "rules": [
            {"type": "condicao", "first": 3, "last": 2, "summary": " Multa por atraso "},
            {"type": "inventado", "first": 2, "last": 2, "summary": "y"},
            {"type": "prazo", "first": 1, "last": 9, "summary": "fora do bloco"},
        ]
    }
    responses += [
        httpx.Response(429, json={"error": {"details": [{"retryDelay": "3s"}]}}),
        httpx.Response(200, json=_answer(json.dumps(rules))),
    ]
    found = await llm.extract_rules_from_chunk(text, sentences, range(1, 3))
    assert found == [llm.ExtractedRule("condicao", 8, 49, "Multa por atraso")]
    assert text[8:49] == "Pagar em até 10 dias; caso atrase, multa."
    assert len(requests) == 2
    assert requests[-1].headers["x-goog-api-key"] == "chave-teste"
    assert requests[-1].url.path.endswith(":generateContent")
    body = json.loads(requests[-1].content)
    assert "[2] Pagar em até 10 dias;" in body["contents"][0]["parts"][0]["text"]
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}


async def test_daily_quota_is_not_retried(gemini):
    responses, requests = gemini
    error = {"error": {"details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}]}}
    responses.append(httpx.Response(429, json=error))
    with pytest.raises(llm.LlmApiError, match="cota diária"):
        await llm.extract_rules_from_chunk("Texto.", llm.split_sentences("Texto."), range(1))
    assert len(requests) == 1


async def test_invalid_key_gives_friendly_message(gemini):
    responses, _ = gemini
    error = {"error": {"message": "API key not valid. Please pass a valid key."}}
    responses.append(httpx.Response(400, json=error))
    with pytest.raises(llm.LlmApiError, match="GEMINI_API_KEY"):
        await llm.extract_rules_from_chunk("Texto.", llm.split_sentences("Texto."), range(1))


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


async def test_slow_request_is_hedged(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_hedge_seconds", 0.01)
    calls = 0
    slow = asyncio.Event()

    class Client:
        async def post(self, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                await slow.wait()
            return httpx.Response(200, json=_answer("ok"))

    response = await llm._post_hedged(Client(), "chave-teste", {})
    assert response.status_code == 200
    assert calls == 2


async def test_failed_chunk_cancels_the_others(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr("chave-teste"))
    monkeypatch.setattr(get_settings(), "llm_chunk_chars", 20)
    monkeypatch.setattr(get_settings(), "llm_max_concurrency", 4)
    pending: list[asyncio.Task] = []

    async def extract(text, sentences, ids, datasets=None):
        if ids.start == 0:
            await asyncio.sleep(0)
            raise llm.LlmApiError("cota")
        pending.append(asyncio.current_task())
        await asyncio.Event().wait()

    monkeypatch.setattr(llm, "extract_rules_from_chunk", extract)
    with pytest.raises(llm.LlmApiError):
        await llm.extract_rules("Primeira frase longa. Segunda frase longa. Terceira frase.")
    await asyncio.sleep(0)
    assert pending and all(t.cancelled() for t in pending)


@pytest.mark.parametrize("stream", [False, True])
async def test_second_key_handles_daily_quota(gemini, monkeypatch, stream):
    responses, requests = gemini
    monkeypatch.setattr(get_settings(), "gemini_api_key_2", SecretStr("segunda-chave"))
    responses.append(httpx.Response(429, json={"quotaId": "RequestsPerDay"}))
    if stream:
        responses.append(httpx.Response(200, text=f"data: {json.dumps(_answer('ok'))}\n\n"))
        assert "".join([part async for part in llm.stream_chat("contexto", [])]) == "ok"
    else:
        responses.append(httpx.Response(200, json=_answer("ok")))
        assert await llm._generate({}) == _answer("ok")
    assert [r.headers["x-goog-api-key"] for r in requests] == ["chave-teste", "segunda-chave"]
    assert llm._select_key() == "segunda-chave"


async def test_key_pool_rotates_and_stops_when_both_exhausted(gemini, monkeypatch):
    responses, requests = gemini
    monkeypatch.setattr(get_settings(), "gemini_api_key_2", SecretStr("segunda-chave"))
    responses.extend([httpx.Response(200, json=_answer("ok")) for _ in range(2)])
    await llm._generate({})
    await llm._generate({})
    assert [r.headers["x-goog-api-key"] for r in requests] == ["chave-teste", "segunda-chave"]
    responses.extend([httpx.Response(429, json={"quotaId": "RequestsPerDay"}) for _ in range(2)])
    with pytest.raises(llm.LlmApiError, match="cota"):
        await llm._generate({})
    with pytest.raises(llm.LlmApiError, match="cota"):
        await llm._generate({})
    assert len(requests) == 4


def test_duplicate_keys_and_cooldown_expiration(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr("same"))
    monkeypatch.setattr(get_settings(), "gemini_api_key_2", SecretStr("same"))
    assert llm._configured_keys() == ["same"]
    monkeypatch.setattr(get_settings(), "gemini_api_key_2", SecretStr("other"))
    monkeypatch.setattr(llm.time, "monotonic", lambda: 100.0)
    assert llm._quota_failover("same", 429, '{"retryDelay": "3s"}', 0)
    assert llm._select_key() == "other"
    monkeypatch.setattr(llm.time, "monotonic", lambda: 105.0)
    assert llm._select_key() == "same"


@pytest.mark.parametrize("stream", [False, True])
async def test_third_key_handles_two_exhausted_keys(gemini, monkeypatch, stream):
    responses, requests = gemini
    monkeypatch.setattr(get_settings(), "gemini_api_key_2", SecretStr("segunda-chave"))
    monkeypatch.setattr(get_settings(), "gemini_api_key_3", SecretStr("terceira-chave"))
    responses.extend([httpx.Response(429, json={"quotaId": "RequestsPerDay"}) for _ in range(2)])
    if stream:
        responses.append(httpx.Response(200, text=f"data: {json.dumps(_answer('ok'))}\n\n"))
        assert "".join([part async for part in llm.stream_chat("contexto", [])]) == "ok"
    else:
        responses.append(httpx.Response(200, json=_answer("ok")))
        assert await llm._generate({}) == _answer("ok")
    assert [r.headers["x-goog-api-key"] for r in requests] == [
        "chave-teste", "segunda-chave", "terceira-chave",
    ]
    assert llm._select_key() == "terceira-chave"


def test_three_keys_rotate(gemini, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key_2", SecretStr("segunda-chave"))
    monkeypatch.setattr(get_settings(), "gemini_api_key_3", SecretStr("terceira-chave"))
    assert [llm._select_key() for _ in range(4)] == [
        "chave-teste", "segunda-chave", "terceira-chave", "chave-teste",
    ]


async def test_resume_only_sends_missing_packages(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr("test"))
    monkeypatch.setattr(get_settings(), "llm_chunk_chars", 20)
    monkeypatch.setattr(get_settings(), "llm_chunk_overlap", 0)
    monkeypatch.setattr(get_settings(), "llm_max_concurrency", 1)
    text = "Primeira frase longa. Segunda frase longa. Terceira frase longa."
    calls, saved, progress = [], {}, []
    fail = True

    async def extract(text, sentences, ids, datasets):
        calls.append(ids.start)
        if fail and ids.start > 0:
            raise llm.LlmApiError("overloaded")
        # An empty successful package must also be remembered.
        return [] if ids.start == 0 else [llm.ExtractedRule(
            "prazo", sentences[ids.start].start, sentences[ids.start].end, "Prazo",
        )]

    async def save(value):
        saved.clear()
        saved.update(json.loads(json.dumps(value)))

    async def report(done, total):
        progress.append((done, total))

    monkeypatch.setattr(llm, "extract_rules_from_chunk", extract)
    with pytest.raises(llm.LlmApiError):
        await llm.extract_rules(text, on_checkpoint=save)
    assert len(saved["completed"]) == 1
    calls.clear()
    fail = False
    rules = await llm.extract_rules(text, checkpoint=saved, on_checkpoint=save, on_progress=report)
    assert 0 not in calls and len(calls) == 2 and len(rules) == 2
    assert progress[0] == (1, 3) and progress[-1] == (3, 3)
    calls.clear()
    assert await llm.extract_rules(text, checkpoint=saved) == rules
    assert calls == []
    await llm.extract_rules(text + " Quarta frase longa.", checkpoint=saved)
    assert 0 in calls


async def test_incomplete_package_is_not_success(gemini):
    responses, _ = gemini
    responses.append(httpx.Response(200, json=_answer('{"rules": []}', "MAX_TOKENS")))
    with pytest.raises(llm.LlmApiError, match="Resposta incompleta"):
        await llm.extract_rules_from_chunk("Texto.", llm.split_sentences("Texto."), range(1))
