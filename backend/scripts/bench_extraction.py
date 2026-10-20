"""Mede a extração de regras sobre o texto de um documento já processado.

Roda só a etapa da IA (a mais lenta) e não grava nada no banco. Para cada chamada ao
Gemini registra a duração e os tokens (entrada, saída e raciocínio).

    cd backend
    PYTHONPATH=. .venv/Scripts/python scripts/bench_extraction.py <document_id>
"""

import asyncio
import sys
import time
import uuid

from sqlalchemy import select

from app.db.models import Document
from app.db.session import SessionLocal
from app.services import ingest, llm


async def main(document_id: str) -> None:
    async with SessionLocal() as db:
        doc = await db.scalar(select(Document).where(Document.id == uuid.UUID(document_id)))
    if doc is None or not doc.full_text:
        sys.exit("Documento não encontrado ou sem texto.")

    calls: list[dict] = []
    generate = llm._generate

    async def timed(payload: dict) -> dict:
        start = time.perf_counter()
        data = await generate(payload)
        usage = data.get("usageMetadata") or {}
        calls.append(
            {
                "s": time.perf_counter() - start,
                "in": usage.get("promptTokenCount", 0),
                "out": usage.get("candidatesTokenCount", 0),
                "think": usage.get("thoughtsTokenCount", 0),
                "model": data.get("modelVersion"),
            }
        )
        return data

    llm._generate = timed
    start = time.perf_counter()
    found = await llm.extract_rules(doc.full_text)
    total = time.perf_counter() - start
    kept = ingest.dedupe_rules(found)

    print(f"{doc.title}: {doc.page_count} páginas, {len(doc.full_text)} caracteres")
    print(f"modelo: {calls[0]['model'] if calls else '?'}")
    for i, c in enumerate(calls, 1):
        print(
            f"  chamada {i:2}: {c['s']:6.1f}s  in={c['in']:6} out={c['out']:6} think={c['think']:6}"
        )
    print(f"chamadas: {len(calls)}  total: {total:.1f}s")
    totals = {k: sum(c[k] for c in calls) for k in ("in", "out", "think")}
    print("tokens: in={in} out={out} think={think}".format(**totals))
    print(f"regras: {len(found)} devolvidas, {len(kept)} mantidas")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
