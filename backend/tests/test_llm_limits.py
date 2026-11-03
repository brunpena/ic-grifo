import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.services import llm, validation_llm


@pytest.fixture(autouse=True)
def isolated_budget(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr("test-key"))
    monkeypatch.setattr(get_settings(), "gemini_api_key_2", SecretStr(""))
    monkeypatch.setattr(llm, "_key_cooldowns", {})
    monkeypatch.setattr(llm, "_key_cursor", 0)
    monkeypatch.setattr(get_settings(), "llm_max_concurrency", 2)
    monkeypatch.setattr(get_settings(), "llm_rate_limit_per_minute", 1000)
    monkeypatch.setattr(get_settings(), "llm_hedge_seconds", 0)
    llm._limiters.clear()
    yield
    llm._limiters.clear()


def mock_client(monkeypatch, handler):
    client = httpx.AsyncClient
    monkeypatch.setattr(
        llm.httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(handler), **kw)
    )


async def test_generation_and_chat_share_concurrency(monkeypatch):
    active = maximum = calls = 0
    full = asyncio.Event()
    release = asyncio.Event()

    async def handler(request):
        nonlocal active, maximum, calls
        active += 1
        calls += 1
        maximum = max(maximum, active)
        if active == 2:
            full.set()
        try:
            await release.wait()
            if "streamGenerateContent" in request.url.path:
                answer = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
                return httpx.Response(200, text=f"data: {json.dumps(answer)}\n\n")
            return httpx.Response(200, json={"ok": True})
        finally:
            active -= 1

    async def chat():
        return [chunk async for chunk in llm.stream_chat("document", [])]

    mock_client(monkeypatch, handler)
    tasks = [asyncio.create_task(chat())] + [
        asyncio.create_task(llm._generate({})) for _ in range(5)
    ]
    await asyncio.wait_for(full.wait(), 1)
    await asyncio.sleep(0)
    assert calls == 2
    release.set()
    results = await asyncio.gather(*tasks)
    assert results[0] == ["ok"]
    assert maximum == 2
    assert llm._request_limiter().active == 0


async def test_retry_spends_rate_budget_again(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_rate_limit_per_minute", 1)
    monkeypatch.setattr(llm, "_retry_delay", lambda *_: 0)
    limiter = llm._request_limiter()
    limiter.window = 0.03
    starts = []

    async def handler(_request):
        # Measure admission, before scheduling/HTTP overhead (Windows clocks are coarse).
        starts.append(limiter.starts[-1])
        return httpx.Response(429, json={}) if len(starts) == 1 else httpx.Response(200, json={})

    mock_client(monkeypatch, handler)
    await llm._generate({})
    assert len(starts) == 2
    assert starts[1] - starts[0] >= limiter.window
    assert limiter.active == 0


@pytest.mark.parametrize("concurrency,rate", [(1, 1000), (2, 1)])
async def test_hedge_is_skipped_without_spare_capacity_or_quota(monkeypatch, concurrency, rate):
    monkeypatch.setattr(get_settings(), "llm_max_concurrency", concurrency)
    monkeypatch.setattr(get_settings(), "llm_rate_limit_per_minute", rate)
    monkeypatch.setattr(get_settings(), "llm_hedge_seconds", 0.005)
    started = asyncio.Event()
    finish = asyncio.Event()
    calls = 0

    class Client:
        async def post(self, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            started.set()
            await finish.wait()
            return httpx.Response(200)

    task = asyncio.create_task(llm._post_hedged(Client(), "test", {}))
    await asyncio.wait_for(started.wait(), 1)
    await asyncio.sleep(0.02)
    assert calls == 1
    finish.set()
    await task
    assert llm._request_limiter().active == 0


async def test_cancelled_request_and_waiter_release_capacity(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_max_concurrency", 1)
    started = asyncio.Event()

    class Client:
        async def post(self, *_args, **_kwargs):
            started.set()
            await asyncio.Event().wait()

    first = asyncio.create_task(llm._post_hedged(Client(), "test", {}))
    await asyncio.wait_for(started.wait(), 1)
    second = asyncio.create_task(llm._post_hedged(Client(), "test", {}))
    await asyncio.sleep(0)
    first.cancel()
    second.cancel()
    await asyncio.gather(first, second, return_exceptions=True)
    limiter = llm._request_limiter()
    assert limiter.active == 0
    assert await limiter.acquire(wait=False)
    await limiter.release()


async def test_column_batches_overlap_and_preserve_order_and_uncertainty(monkeypatch):
    columns = [{"name": f"column_{i}", "type": "text"} for i in range(81)]
    all_started = asyncio.Event()
    calls = 0

    async def interpret(_system, payload):
        nonlocal calls
        calls += 1
        if calls == 3:
            all_started.set()
        await asyncio.wait_for(all_started.wait(), 1)
        assert len(payload["context"]) == 81
        items = [{"name": c["name"], "meaning": c["name"]} for c in payload["columns"]]
        if items[0]["name"] == "column_0":
            items.append(items[0])
        return {"columns": items}

    monkeypatch.setattr(validation_llm, "_json", interpret)
    result = await validation_llm.interpret_columns("dataset", columns)
    assert [c["name"] for c in result] == [c["name"] for c in columns]
    assert result[0]["semantic"]["confidence"] == "low"
    assert "duplicadas" in result[0]["semantic"]["reason"]
    assert result[40]["semantic"]["meaning"] == "column_40"
