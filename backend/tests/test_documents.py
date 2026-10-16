import asyncio
import json
import uuid

import httpx
import pymupdf
import pytest

from app.main import app
from app.services import llm
from app.services.ingest import locate_rules
from app.services.llm import ExtractedRule, TextChunk, split_chunks
from app.services.pdf_text import PdfReadError, extract_pdf
from app.services.text_match import find_excerpt

PARAGRAPHS = [
    "CLÁUSULA PRIMEIRA - DO OBJETO",
    "A contratada deverá entregar o relatório mensal em até 10 dias úteis.",
    "É vedada a subcontratação do objeto sem autorização por escrito.",
]


def make_pdf(pages: int = 2) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page(width=595, height=842)
        y = 72
        for text in PARAGRAPHS:
            page.insert_textbox(pymupdf.Rect(72, y, 523, y + 60), text, fontsize=11)
            y += 70
    return doc.tobytes()


# ----- unidades -----


def test_extract_pdf_offsets_match_words():
    result = extract_pdf(make_pdf())
    assert len(result.pages) == 2
    assert all(result.full_text[w.char_start : w.char_end] == w.text for w in result.words)
    assert "relatório mensal" in result.full_text
    first, second = result.pages
    assert first.char_end <= second.char_start


def test_extract_pdf_rejects_invalid_and_empty():
    with pytest.raises(PdfReadError):
        extract_pdf(b"%PDF-nao-e-pdf")
    empty = pymupdf.open()
    empty.new_page()
    with pytest.raises(PdfReadError, match="texto"):
        extract_pdf(empty.tobytes())


def test_find_excerpt_tolerates_whitespace_and_dashes():
    text = "A contratada deverá\nentregar  o relatório – mensal."
    assert find_excerpt(text, "A contratada deverá") == (0, 19)
    start, end = find_excerpt(text, "deverá entregar o relatório - mensal")
    assert text[start:end] == "deverá\nentregar  o relatório – mensal"
    assert find_excerpt(text, "algo que não existe") is None


def test_split_chunks_cover_text_with_overlap():
    text = "\n\n".join(f"Parágrafo {i} " + "x" * 80 for i in range(50))
    chunks = split_chunks(text, size=1000, overlap=200)
    assert chunks[0].start == 0
    assert chunks[-1].start + len(chunks[-1].text) == len(text)
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert b.start < a.start + len(a.text)  # há sobreposição
        assert text[a.start : a.start + len(a.text)] == a.text


def test_locate_rules_drops_duplicates_from_overlapping_chunks():
    text = "Antes. A contratada deverá pagar em 30 dias. Depois."
    rule = ExtractedRule("obrigacao", "A contratada deverá pagar em 30 dias.", "Pagar em 30 dias")
    located = locate_rules(
        text,
        [(TextChunk(0, text), rule), (TextChunk(5, text[5:]), rule)]
        + [(TextChunk(0, text), ExtractedRule("prazo", "trecho inexistente", "x"))],
    )
    assert len(located) == 1
    assert text[located[0][1] : located[0][2]] == rule.excerpt


# ----- fluxo completo, com a IA simulada -----


@pytest.fixture
def fake_llm(monkeypatch):
    async def extract(text, on_progress=None):
        if on_progress:
            await on_progress(1, 1)
        chunk = TextChunk(0, text)
        return [
            (
                chunk,
                ExtractedRule("prazo", "em até 10 dias úteis", "Relatório em até 10 dias úteis"),
            ),
            (
                chunk,
                ExtractedRule(
                    "proibicao", "É vedada a subcontratação do objeto", "Sem subcontratar"
                ),
            ),
        ]

    async def chat(context, history):
        assert "[Página 1]" in context and "R1" in context
        for part in ["O prazo é de 10 dias úteis ", "[R1]", "."]:
            yield part

    monkeypatch.setattr(llm, "extract_rules", extract)
    monkeypatch.setattr(llm, "stream_chat", chat)


async def _login(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Ana",
            "email": f"doc-{uuid.uuid4().hex[:8]}@exemplo.com",
            "password": "senha-forte-1",
        },
    )
    assert resp.status_code == 201


async def _wait_ready(client: httpx.AsyncClient, doc_id: str) -> dict:
    for _ in range(100):
        body = (await client.get(f"/api/v1/documents/{doc_id}")).json()
        if body["status"] in ("ready", "error"):
            return body
        await asyncio.sleep(0.05)
    raise AssertionError("documento não terminou de processar")


@pytest.mark.db
async def test_upload_extract_rules_and_chat(migrated_db, client, fake_llm):
    await _login(client)
    resp = await client.post(
        "/api/v1/documents", files={"file": ("contrato.pdf", make_pdf(), "application/pdf")}
    )
    assert resp.status_code == 202
    doc = resp.json()
    assert doc["status"] == "processing"

    doc = await _wait_ready(client, doc["id"])
    assert doc["status"] == "ready" and doc["page_count"] == 2

    rules = (await client.get(f"/api/v1/documents/{doc['id']}/rules")).json()
    assert [r["type"] for r in rules] == ["prazo", "proibicao"]
    box = rules[0]["boxes"][0]
    assert rules[0]["page"] == 1 and box["page"] == 1
    assert 0 < box["x"] < 1 and 0 < box["y"] < 1 and 0 < box["width"] < 1

    resp = await client.patch(f"/api/v1/rules/{rules[0]['id']}", json={"status": "validada"})
    assert resp.json()["status"] == "validada"

    # Regra manual a partir de um trecho selecionado na página 2.
    resp = await client.post(
        f"/api/v1/documents/{doc['id']}/rules",
        json={
            "type": "obrigacao",
            "summary": "Entregar relatório",
            "page": 2,
            "excerpt": "A contratada deverá  entregar o relatório mensal",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["page"] == 2 and resp.json()["origin"] == "manual"
    resp = await client.post(
        f"/api/v1/documents/{doc['id']}/rules",
        json={"type": "obrigacao", "summary": "x", "page": 1, "excerpt": "trecho que não existe"},
    )
    assert resp.status_code == 422

    # Conversa por SSE.
    events = []
    async with client.stream(
        "POST", f"/api/v1/documents/{doc['id']}/messages", json={"content": "Qual o prazo?"}
    ) as stream:
        event = None
        async for line in stream.aiter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((event, json.loads(line.split(":", 1)[1])))
    assert [e for e, _ in events][-1] == "done"
    final = events[-1][1]
    assert final["content"] == "O prazo é de 10 dias úteis."
    assert [c["id"] for c in final["citations"]] == [rules[0]["id"]]

    history = (await client.get(f"/api/v1/documents/{doc['id']}/messages")).json()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[1]["citations"][0]["summary"] == "Relatório em até 10 dias úteis"


@pytest.mark.db
async def test_documents_are_private_and_validated(migrated_db, client, fake_llm):
    await _login(client)
    resp = await client.post(
        "/api/v1/documents", files={"file": ("x.txt", b"nao sou pdf", "text/plain")}
    )
    assert resp.status_code == 422
    doc = (
        await client.post(
            "/api/v1/documents", files={"file": ("c.pdf", make_pdf(1), "application/pdf")}
        )
    ).json()
    await _wait_ready(client, doc["id"])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as other:
        await _login(other)
        assert (await other.get(f"/api/v1/documents/{doc['id']}")).status_code == 404
        assert (await other.get(f"/api/v1/documents/{doc['id']}/rules")).status_code == 404
        assert (await other.get("/api/v1/documents")).json() == []
    client.cookies.clear()
    assert (await client.get(f"/api/v1/documents/{doc['id']}")).status_code == 401
