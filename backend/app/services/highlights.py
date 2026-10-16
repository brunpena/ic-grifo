"""Retângulos do grifo de cada regra, a partir das palavras que o trecho cobre."""

import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Page, Word


async def rule_boxes(
    db: AsyncSession, document_id: uuid.UUID, ranges: dict[uuid.UUID, tuple[int, int]]
) -> dict[uuid.UUID, list[dict]]:
    """Para cada regra, uma lista de {page, x, y, width, height} em frações da página.

    Palavras vizinhas na mesma linha viram um único retângulo.
    """
    if not ranges:
        return {}
    low = min(s for s, _ in ranges.values())
    high = max(e for _, e in ranges.values())
    pages = {
        p.page_number: (p.width, p.height)
        for p in await db.scalars(select(Page).where(Page.document_id == document_id))
    }
    words = (
        await db.scalars(
            select(Word)
            .where(Word.document_id == document_id, Word.char_end > low, Word.char_start < high)
            .order_by(Word.char_start)
        )
    ).all()

    boxes: dict[uuid.UUID, list[dict]] = defaultdict(list)
    for rule_id, (start, end) in ranges.items():
        current: list[float] | None = None  # [page, x0, y0, x1, y1]
        for w in words:
            if w.char_end <= start or w.char_start >= end:
                continue
            same_line = (
                current is not None
                and current[0] == w.page
                and abs(current[2] - w.y0) < 0.5 * (w.y1 - w.y0)
            )
            if same_line:
                current[3] = max(current[3], w.x1)
                current[4] = max(current[4], w.y1)
            else:
                if current is not None:
                    boxes[rule_id].append(_to_fraction(current, pages))
                current = [w.page, w.x0, w.y0, w.x1, w.y1]
        if current is not None:
            boxes[rule_id].append(_to_fraction(current, pages))
    return boxes


def _to_fraction(box: list[float], pages: dict[int, tuple[float, float]]) -> dict:
    page, x0, y0, x1, y1 = box
    width, height = pages.get(int(page), (1.0, 1.0))
    return {
        "page": int(page),
        "x": x0 / width,
        "y": y0 / height,
        "width": (x1 - x0) / width,
        "height": (y1 - y0) / height,
    }


async def page_range(db: AsyncSession, document_id: uuid.UUID, page: int) -> tuple[int, int] | None:
    """Início e fim (em `full_text`) do texto de uma página."""
    start, end = (
        await db.execute(
            select(func.min(Word.char_start), func.max(Word.char_end)).where(
                Word.document_id == document_id, Word.page == page
            )
        )
    ).one()
    return None if start is None else (start, end)
