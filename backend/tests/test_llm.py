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
    llm._limiters.clear()
    yield
    llm._limiters.clear()


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


def _prompt(**kwargs) -> llm.ExcerptPrompt:
    values = {
        "excerpt": "Contratos acima de R$ 50 mil exigem garantia.",
        "page": 3,
        "context": "CLÁUSULA 5. Contratos acima de R$ 50 mil exigem garantia.",
        "datasets": [
            llm.DatasetPrompt(
                "contratos", 2, [{"name": "Valor", "type": "decimal", "examples": ["10"]}]
            )
        ],
        "history": [],
    }
    return llm.ExcerptPrompt(**{**values, **kwargs})


async def test_analyze_excerpt_parses_json_and_retries_rate_limit(gemini):
    responses, requests = gemini
    answer = {
        "reply": "É uma condição verificável.",
        "is_rule": True,
        "verifiable": True,
        "type": "inventado",
        "summary": "  Exigir   garantia acima de 50 mil ",
        "interpretation": "Contratos com Valor acima de 50 mil.",
        "reason": "A coluna Valor existe.",
        "dataset": "contratos",
        "logic": "talvez",
        "conditions": [
            {"column": "Valor", "op": "gt", "value": "50000"},
            {"column": "Valor", "op": "DROP TABLE", "value": "1"},
        ],
    }
    responses += [
        httpx.Response(429, json={"error": {"details": [{"retryDelay": "3s"}]}}),
        httpx.Response(200, json=_answer(json.dumps(answer))),
    ]
    history = [
        {"role": "user", "content": "Analise o trecho grifado."},
        {"role": "assistant", "content": "É uma condição."},
        {"role": "user", "content": "Considere só acima de 60 mil."},
    ]
    current = {"category": "csv", "type": "condicao", "summary": "x", "query": None}
    found = await llm.analyze_excerpt(_prompt(history=history, current=current))
    assert found.verifiable and found.type == "outro"
    assert found.summary == "Exigir garantia acima de 50 mil"
    assert found.query == {
        "dataset": "contratos",
        "logic": "and",
        "conditions": [{"column": "Valor", "op": "gt", "value": "50000"}],
    }
    assert len(requests) == 2
    assert requests[-1].headers["x-goog-api-key"] == "chave-teste"
    assert requests[-1].url.path.endswith(":generateContent")
    body = json.loads(requests[-1].content)
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    first = body["contents"][0]["parts"][0]["text"]
    assert '<base nome="contratos" linhas="2">' in first
    assert '<contexto pagina="3">' in first and "<trecho_grifado>" in first
    last = body["contents"][-1]["parts"][0]["text"]
    assert "<proposta_atual>" in last and last.endswith("Considere só acima de 60 mil.")
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}


async def test_non_verifiable_excerpt_has_no_query(gemini):
    responses, _ = gemini
    answer = {
        "reply": "Não há coluna sobre a assinatura do termo.",
        "is_rule": True,
        "verifiable": False,
        "type": "obrigacao",
        "summary": "Assinar o termo",
        "interpretation": "",
        "reason": "Sem coluna de assinatura.",
        "dataset": "contratos",
        "logic": "and",
        "conditions": [{"column": "Valor", "op": "gt", "value": "1"}],
    }
    responses.append(httpx.Response(200, json=_answer(json.dumps(answer))))
    found = await llm.analyze_excerpt(_prompt())
    assert not found.verifiable and found.query is None and found.type == "obrigacao"


async def test_daily_quota_is_not_retried(gemini):
    responses, requests = gemini
    error = {"error": {"details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}]}}
    responses.append(httpx.Response(429, json=error))
    with pytest.raises(llm.LlmApiError, match="cota diária"):
        await llm.analyze_excerpt(_prompt())
    assert len(requests) == 1


async def test_invalid_key_gives_friendly_message(gemini):
    responses, _ = gemini
    error = {"error": {"message": "API key not valid. Please pass a valid key."}}
    responses.append(httpx.Response(400, json=error))
    with pytest.raises(llm.LlmApiError, match="GEMINI_API_KEY"):
        await llm.analyze_excerpt(_prompt())


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
        await llm.analyze_excerpt(_prompt())


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
        "chave-teste",
        "segunda-chave",
        "terceira-chave",
    ]
    assert llm._select_key() == "terceira-chave"


def test_three_keys_rotate(gemini, monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key_2", SecretStr("segunda-chave"))
    monkeypatch.setattr(get_settings(), "gemini_api_key_3", SecretStr("terceira-chave"))
    assert [llm._select_key() for _ in range(4)] == [
        "chave-teste",
        "segunda-chave",
        "terceira-chave",
        "chave-teste",
    ]


@pytest.mark.parametrize("stream", [False, True])
async def test_third_credential_overload_is_not_reported_as_daily_quota(
    gemini, monkeypatch, stream
):
    responses, requests = gemini
    monkeypatch.setattr(get_settings(), "gemini_api_key_2", SecretStr("second"))
    monkeypatch.setattr(get_settings(), "gemini_api_key_3", SecretStr("third"))
    responses.extend(
        [
            httpx.Response(429, json={"quotaId": "RequestsPerDay"}),
            httpx.Response(429, json={"quotaId": "RequestsPerDay"}),
            httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}}),
        ]
    )
    if stream:
        responses.append(httpx.Response(200, text=f"data: {json.dumps(_answer('ok'))}\n\n"))
        assert "".join([part async for part in llm.stream_chat("context", [])]) == "ok"
    else:
        responses.append(httpx.Response(200, json=_answer("ok")))
        assert await llm._generate({}) == _answer("ok")
    assert [r.headers["x-goog-api-key"] for r in requests] == [
        "chave-teste",
        "second",
        "third",
        "third",
    ]


def test_daily_cooldown_uses_provider_release_time_and_is_scoped_to_model(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("first"))
    monkeypatch.setattr(settings, "gemini_api_key_2", SecretStr("second"))
    monkeypatch.setattr(settings, "gemini_model", "model-a")
    now = [100.0]
    monkeypatch.setattr(llm.time, "monotonic", lambda: now[0])
    body = json.dumps({"quotaId": "RequestsPerDay", "retryDelay": "19307s"})
    assert llm._quota_failover("first", 429, body, 0)
    assert not llm._quota_failover("second", 429, body, 0)
    with pytest.raises(llm.LlmApiError, match="cota diária"):
        llm._select_key()
    # Alterar o modelo não herda o bloqueio do modelo anterior.
    monkeypatch.setattr(settings, "gemini_model", "model-b")
    assert llm._select_key() in {"first", "second"}
    monkeypatch.setattr(settings, "gemini_model", "model-a")
    now[0] = 100.0 + 19309
    assert llm._select_key() in {"first", "second"}


def test_quota_logs_identify_slots_without_exposing_credentials(monkeypatch, caplog):
    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr("private-credential-one"))
    monkeypatch.setattr(get_settings(), "gemini_api_key_2", SecretStr("private-credential-two"))
    llm._quota_failover("private-credential-one", 429, '{"quotaId":"RequestsPerDay"}', 0)
    record = next(r for r in caplog.records if r.message == "gemini_quota_limited")
    assert record.credential_slot == 1 and record.configured_credentials == 2
    assert "private-credential" not in str(record.__dict__)


async def test_incomplete_answer_is_not_success(gemini):
    responses, _ = gemini
    responses.append(httpx.Response(200, json=_answer('{"reply": "Parcial', "MAX_TOKENS")))
    with pytest.raises(llm.LlmApiError, match="inválida"):
        await llm.analyze_excerpt(_prompt())
