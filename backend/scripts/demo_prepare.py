"""Deixa a análise da Portaria nº 21/2012 pronta para demonstração, sem o Gemini.

Usa a análise mais recente que já tem o PDF da portaria e a base do Sisu
(chamada_regular_sisu_2022_1) e roda, com as respostas prontas de
`app/services/llm_mock.py`: extração das regras, geração das buscas e validação.

Uso (na pasta backend):
    .venv\\Scripts\\python.exe scripts\\demo_prepare.py
"""

import asyncio
import os
import sys
from pathlib import Path

os.environ["LLM_MOCK"] = "true"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select, update  # noqa: E402

from app.db.models import Dataset, Document, Rule  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services import ingest  # noqa: E402

TITLE = "PORTARIA NORMATIVA Nº 21"


async def find_document() -> Document | None:
    async with SessionLocal() as db:
        documents = (
            await db.scalars(
                select(Document)
                .where(Document.title.startswith(TITLE))
                .order_by(Document.created_at.desc())
            )
        ).all()
        for document in documents:
            datasets = (
                await db.scalars(
                    select(Dataset).where(
                        Dataset.analysis_id == document.analysis_id, Dataset.status == "ready"
                    )
                )
            ).all()
            if any(any(c["name"] == "APROVADO" for c in d.columns or []) for d in datasets):
                return document
    return None


async def main() -> None:
    document = await find_document()
    if document is None:
        print("Nenhuma análise com o PDF da Portaria 21 e a base do Sisu foi encontrada.")
        print("Envie os dois arquivos de backend/dados numa análise e rode de novo.")
        return
    print(f"Análise {document.analysis_id}")
    print(f"Documento {document.id} ({document.status})")

    async with SessionLocal() as db:
        await db.execute(delete(Rule).where(Rule.document_id == document.id))
        await db.execute(
            update(Document)
            .where(Document.id == document.id)
            .values(status="processing", status_message=None, extraction_checkpoint=None)
        )
        await db.commit()

    print("Extraindo regras e gerando buscas...")
    await ingest.process_document(document.id)
    print("Validando as regras na base...")
    await ingest._run_validation(document.id)
    await ingest._set_status(document.id, "ready")

    async with SessionLocal() as db:
        final = await db.get(Document, document.id)
        rules = (await db.scalars(select(Rule).where(Rule.document_id == document.id))).all()
        print(f"Status: {final.status} {final.status_message or ''}")
        print(f"Regras: {len(rules)}")
        for rule in sorted(rules, key=lambda r: r.char_start):
            status = (rule.validation or {}).get("status", "-")
            print(f"  [{status:>12}] {rule.summary}")
    print("Pronto. Abra essa análise no front (a mais recente da Portaria 21).")


asyncio.run(main())
