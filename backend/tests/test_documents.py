import asyncio
import json
import uuid

import httpx
import pymupdf
import pytest

from app.main import app
from app.services import llm, safe_fetch
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


# ----- fluxo completo, com a IA simulada -----


@pytest.fixture
def fake_llm(monkeypatch):
    prompts: list[llm.ExcerptPrompt] = []

    async def analyze(prompt):
        prompts.append(prompt)
        return llm.ExcerptAnswer(
            reply="É um prazo, mas não há base para verificá-lo.",
            is_rule=True,
            verifiable=False,
            type="prazo",
            summary="Relatório em até 10 dias úteis",
            interpretation="O relatório mensal deve ser entregue em até 10 dias úteis.",
            reason="Nenhuma base registra a entrega do relatório.",
            query=None,
        )

    async def chat(context, history):
        assert "[Página 1]" in context and "R1" in context
        for part in ["O prazo é de 10 dias úteis ", "[R1]", "."]:
            yield part

    monkeypatch.setattr(llm, "analyze_excerpt", analyze)
    monkeypatch.setattr(llm, "stream_chat", chat)
    return prompts


async def approve(client: httpx.AsyncClient, doc_id: str, excerpt: str, **fields) -> dict:
    """Aprova uma regra de um trecho grifado (única forma de criar regras)."""
    body = {"type": "obrigacao", "summary": excerpt[:40], "page": 1, "excerpt": excerpt}
    resp = await client.post(f"/api/v1/documents/{doc_id}/rules", json={**body, **fields})
    assert resp.status_code == 201, resp.text
    return resp.json()


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
async def test_upload_highlight_approve_and_chat(migrated_db, client, fake_llm):
    await _login(client)
    resp = await client.post(
        "/api/v1/documents", files={"file": ("contrato.pdf", make_pdf(), "application/pdf")}
    )
    assert resp.status_code == 202
    doc = resp.json()
    assert doc["status"] == "processing"

    # Sem extração automática: o documento fica pronto para grifar, sem regras.
    doc = await _wait_ready(client, doc["id"])
    assert doc["status"] == "ready" and doc["page_count"] == 2
    url = f"/api/v1/documents/{doc['id']}"
    assert (await client.get(f"{url}/rules")).json() == []

    # A IA analisa só o trecho grifado; nada é salvo.
    resp = await client.post(
        f"{url}/excerpt-analysis", json={"page": 1, "excerpt": "em até 10 dias úteis"}
    )
    assert resp.status_code == 200, resp.text
    analysis = resp.json()
    assert analysis["reply"].startswith("É um prazo")
    proposal = analysis["proposal"]
    assert proposal["category"] == "geral" and proposal["query"] is None
    assert fake_llm[0].excerpt == "em até 10 dias úteis" and fake_llm[0].page == 1
    assert "CLÁUSULA PRIMEIRA" in fake_llm[0].context
    assert (await client.get(f"{url}/rules")).json() == []
    resp = await client.post(
        f"{url}/excerpt-analysis",
        json={
            "page": 1,
            "excerpt": "em até 10 dias úteis",
            "messages": [{"role": "assistant", "content": "oi"}],
        },
    )
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "invalid_messages"
    resp = await client.post(
        f"{url}/excerpt-analysis", json={"page": 1, "excerpt": "trecho que não existe"}
    )
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "excerpt_not_found"

    # A aprovação cria a regra, já validada e ligada ao trecho.
    prazo = await approve(
        client,
        doc["id"],
        "em até 10 dias úteis",
        type=proposal["type"],
        summary=proposal["summary"],
        interpretation=proposal["interpretation"],
        category="geral",
        origin="ia",
    )
    assert prazo["status"] == "validada" and prazo["category"] == "geral"
    assert prazo["origin"] == "ia" and prazo["query"] is None
    assert prazo["interpretation"].startswith("O relatório mensal")
    box = prazo["boxes"][0]
    assert prazo["page"] == 1 and box["page"] == 1
    assert 0 < box["x"] < 1 and 0 < box["y"] < 1 and 0 < box["width"] < 1

    manual = await approve(
        client, doc["id"], "A contratada deverá  entregar o relatório mensal", page=2
    )
    assert manual["page"] == 2 and manual["origin"] == "manual"
    resp = await client.post(
        f"{url}/rules",
        json={"type": "obrigacao", "summary": "x", "page": 1, "excerpt": "trecho que não existe"},
    )
    assert resp.status_code == 422
    # Regra verificável sem busca não é aceita.
    resp = await client.post(
        f"{url}/rules",
        json={
            "type": "proibicao",
            "summary": "Sem subcontratar",
            "page": 1,
            "excerpt": "É vedada a subcontratação do objeto",
            "category": "csv",
        },
    )
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "invalid_query"
    rules = (await client.get(f"{url}/rules")).json()
    assert [r["id"] for r in rules] == [prazo["id"], manual["id"]]

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
    assert [c["id"] for c in final["citations"]] == [prazo["id"]]

    history = (await client.get(f"/api/v1/documents/{doc['id']}/messages")).json()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[1]["citations"][0]["summary"] == "Relatório em até 10 dias úteis"


@pytest.mark.db
async def test_documents_are_private_and_validated(migrated_db, client, fake_llm):
    await _login(client)
    resp = await client.post(
        "/api/v1/documents",
        files={"file": ("x.docx", b"PK\x03\x04", "application/octet-stream")},
    )
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "unsupported_format"
    blank = pymupdf.open()
    blank.new_page()
    resp = await client.post(
        "/api/v1/documents", files={"file": ("scan.pdf", blank.tobytes(), "application/pdf")}
    )
    assert resp.status_code == 202
    scanned = await _wait_ready(client, resp.json()["id"])
    assert scanned["status"] == "error" and "digitalizado" in scanned["status_message"]
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


@pytest.mark.db
async def test_text_and_link_documents_share_an_analysis(
    migrated_db, client, fake_llm, monkeypatch
):
    await _login(client)
    analysis = (await client.post("/api/v1/analyses", json={})).json()

    text = "\n\n".join(PARAGRAPHS)
    resp = await client.post(
        "/api/v1/documents/text", json={"analysis_id": analysis["id"], "content": text}
    )
    assert resp.status_code == 202
    pasted = resp.json()
    assert pasted["source_type"] == "text" and pasted["title"] == PARAGRAPHS[0]
    assert (await _wait_ready(client, pasted["id"]))["status"] == "ready"
    rule = await approve(client, pasted["id"], "É vedada a subcontratação do objeto")
    assert rule["boxes"]  # o grifo funciona no PDF diagramado
    pdf = await client.get(f"/api/v1/documents/{pasted['id']}/file")
    assert pdf.content.startswith(b"%PDF-")

    async def fake_fetch(url, **kwargs):
        if "interno" in url:
            raise safe_fetch.FetchError("Este link aponta para um endereço interno.")
        page = "<html><head><title>Página do edital</title></head><body>"
        page += "".join(f"<p>{p}</p>" for p in PARAGRAPHS) + "</body></html>"
        return safe_fetch.FetchedFile(page.encode(), "text/html", "utf-8", "edital", url)

    monkeypatch.setattr(safe_fetch, "fetch_url", fake_fetch)
    resp = await client.post(
        "/api/v1/documents/url",
        json={"analysis_id": analysis["id"], "url": "https://exemplo.com/edital"},
    )
    assert resp.status_code == 202
    linked = resp.json()
    linked = await _wait_ready(client, linked["id"])
    assert linked["source_type"] == "html" and linked["title"] == "Página do edital"
    assert linked["source_url"] == "https://exemplo.com/edital"

    resp = await client.post("/api/v1/documents/url", json={"url": "http://interno/"})
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "fetch_error"
    resp = await client.post("/api/v1/documents/text", json={"content": "   "})
    assert resp.status_code == 422

    detail = (await client.get(f"/api/v1/analyses/{analysis['id']}")).json()
    assert [d["id"] for d in detail["documents"]] == [pasted["id"], linked["id"]]
    assert detail["title"] == PARAGRAPHS[0]  # a análise ganha o nome do primeiro documento
