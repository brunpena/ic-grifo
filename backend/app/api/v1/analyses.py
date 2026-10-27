"""Análises e as bases de dados (CSV) que elas verificam."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.api.deps import SessionDep, UserDep
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError, PayloadTooLargeError
from app.db.models import Analysis, Dataset, Document, RuleQuery, User
from app.schemas.analyses import (
    AnalysisCreateIn,
    AnalysisDetailOut,
    AnalysisOut,
    AnalysisUpdateIn,
    DatasetOut,
)
from app.schemas.common import error_responses
from app.schemas.documents import DocumentOut
from app.services import ingest, storage
from app.services.datasets import dataset_display_name, fit_to_size

router = APIRouter(tags=["análises"])

# .crdownload: download do Chrome salvo antes de ser renomeado; o conteúdo é o próprio CSV.
CSV_EXTENSIONS = (".csv", ".tsv", ".txt", ".crdownload")


async def owned_analysis(db: SessionDep, analysis_id: uuid.UUID, user: User) -> Analysis:
    analysis = await db.get(Analysis, analysis_id)
    if analysis is None or analysis.user_id != user.id:
        raise NotFoundError("Análise não encontrada.")
    return analysis


async def _owned_dataset(db: SessionDep, dataset_id: uuid.UUID, user: User) -> Dataset:
    dataset = await db.get(Dataset, dataset_id)
    if dataset is None:
        raise NotFoundError("Base de dados não encontrada.")
    await owned_analysis(db, dataset.analysis_id, user)
    return dataset


async def _detail(db: SessionDep, analysis_id: uuid.UUID) -> AnalysisDetailOut:
    analysis = await db.scalar(
        select(Analysis)
        .where(Analysis.id == analysis_id)
        .options(selectinload(Analysis.datasets), selectinload(Analysis.documents))
        .execution_options(populate_existing=True)
    )
    assert analysis is not None
    return AnalysisDetailOut(
        id=analysis.id,
        title=analysis.title,
        created_at=analysis.created_at,
        datasets=[DatasetOut.model_validate(d) for d in analysis.datasets],
        documents=[DocumentOut.model_validate(d) for d in analysis.documents],
    )


# ---------------------------------------------------------------------------
# Análises
# ---------------------------------------------------------------------------


@router.post(
    "/analyses",
    status_code=status.HTTP_201_CREATED,
    summary="Cria uma análise vazia (as bases e os documentos são enviados depois)",
)
async def create_analysis(
    body: AnalysisCreateIn, user: UserDep, db: SessionDep
) -> AnalysisDetailOut:
    analysis = Analysis(user_id=user.id, title=body.title)
    db.add(analysis)
    await db.commit()
    return await _detail(db, analysis.id)


@router.get("/analyses", summary="Análises do usuário, da mais recente à mais antiga")
async def list_analyses(user: UserDep, db: SessionDep) -> list[AnalysisOut]:
    datasets = select(func.count()).where(Dataset.analysis_id == Analysis.id).scalar_subquery()
    documents = select(func.count()).where(Document.analysis_id == Analysis.id).scalar_subquery()
    rows = await db.execute(
        select(Analysis, datasets, documents)
        .where(Analysis.user_id == user.id)
        .order_by(Analysis.created_at.desc())
    )
    return [
        AnalysisOut(
            id=a.id,
            title=a.title,
            dataset_count=n_datasets,
            document_count=n_documents,
            created_at=a.created_at,
        )
        for a, n_datasets, n_documents in rows
    ]


@router.get(
    "/analyses/{analysis_id}",
    summary="A análise com suas bases e documentos",
    responses=error_responses(404),
)
async def get_analysis(analysis_id: uuid.UUID, user: UserDep, db: SessionDep) -> AnalysisDetailOut:
    await owned_analysis(db, analysis_id, user)
    return await _detail(db, analysis_id)


@router.patch(
    "/analyses/{analysis_id}", summary="Renomeia a análise", responses=error_responses(404)
)
async def update_analysis(
    analysis_id: uuid.UUID, body: AnalysisUpdateIn, user: UserDep, db: SessionDep
) -> AnalysisDetailOut:
    analysis = await owned_analysis(db, analysis_id, user)
    analysis.title = body.title.strip() or analysis.title
    await db.commit()
    return await _detail(db, analysis_id)


@router.delete(
    "/analyses/{analysis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui a análise, com as bases, os documentos, as regras e as conversas",
    responses=error_responses(404),
)
async def delete_analysis(analysis_id: uuid.UUID, user: UserDep, db: SessionDep) -> Response:
    analysis = await owned_analysis(db, analysis_id, user)
    document_ids = (
        await db.scalars(select(Document.id).where(Document.analysis_id == analysis_id))
    ).all()
    dataset_ids = (
        await db.scalars(select(Dataset.id).where(Dataset.analysis_id == analysis_id))
    ).all()
    await db.delete(analysis)
    await db.commit()
    await storage.delete_files(
        [storage.pdf_name(i) for i in document_ids] + [storage.dataset_name(i) for i in dataset_ids]
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Bases de dados
# ---------------------------------------------------------------------------


@router.post(
    "/analyses/{analysis_id}/datasets",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Envia uma base de dados em CSV; o servidor lê em segundo plano",
    description=(
        "Um arquivo por requisição. A base volta em `processing` e passa a `ready` (ou "
        "`error`, com o motivo) depois que o servidor detecta separador, codificação e o tipo "
        "de cada coluna. As linhas ficam só no servidor e são lidas pelas buscas das regras."
    ),
    responses=error_responses(404, 413, 422),
)
async def upload_dataset(
    analysis_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="Arquivo CSV")],
    user: UserDep,
    db: SessionDep,
) -> DatasetOut:
    await owned_analysis(db, analysis_id, user)
    settings = get_settings()
    filename = (file.filename or "base.csv")[:200]
    if not filename.lower().endswith(CSV_EXTENSIONS):
        raise AppError(
            f"“{filename}” não é um CSV. Envie um arquivo .csv.",
            code="not_a_csv",
            status_code=422,
        )
    limit = settings.max_dataset_bytes
    data = await file.read() if limit is None else await file.read(limit + 1)
    if limit is not None and len(data) > limit:
        raise PayloadTooLargeError(
            f"“{filename}” passa do limite de {settings.max_dataset_mb} MB por base."
        )
    if not data.strip():
        raise AppError(f"“{filename}”: o arquivo está vazio.", code="invalid_csv", status_code=422)
    # O que passa do limite do armazenamento fica de fora (corte em fim de linha).
    try:
        storage_limit = await storage.max_file_bytes()
    except storage.StorageError as exc:
        raise AppError(str(exc), code="storage_error", status_code=502) from exc
    if storage_limit is not None:
        data = fit_to_size(data, storage_limit)
        if not data.strip():
            raise AppError(
                f"“{filename}”: a primeira linha já passa do limite do armazenamento.",
                code="invalid_csv",
                status_code=422,
            )

    taken = set(
        (await db.scalars(select(Dataset.name).where(Dataset.analysis_id == analysis_id))).all()
    )
    dataset = Dataset(
        analysis_id=analysis_id,
        name=dataset_display_name(filename, taken),
        filename=filename,
        size_bytes=len(data),
        status="processing",
    )
    db.add(dataset)
    await db.flush()
    try:
        dataset.storage_path = await storage.save_file(
            storage.dataset_name(dataset.id), data, "text/csv"
        )
    except storage.StorageError as exc:
        raise AppError(str(exc), code="storage_error", status_code=502) from exc
    await db.commit()
    await db.refresh(dataset)
    ingest.start_dataset_processing(dataset.id)
    return DatasetOut.model_validate(dataset)


@router.get(
    "/datasets/{dataset_id}",
    summary="Schema e situação da leitura de uma base",
    responses=error_responses(404),
)
async def get_dataset(dataset_id: uuid.UUID, user: UserDep, db: SessionDep) -> DatasetOut:
    return DatasetOut.model_validate(await _owned_dataset(db, dataset_id, user))


@router.delete(
    "/datasets/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a base da análise",
    description="As buscas das regras que usavam esta base ficam sem base (dataset_id nulo).",
    responses=error_responses(404),
)
async def delete_dataset(dataset_id: uuid.UUID, user: UserDep, db: SessionDep) -> Response:
    dataset = await _owned_dataset(db, dataset_id, user)
    await db.execute(
        update(RuleQuery)
        .where(RuleQuery.dataset_id == dataset_id)
        .values(
            state="erro",
            error=f"A base “{dataset.name}” foi removida. Envie de novo e rode a busca.",
            match_count=None,
            matched_rows=[],
        )
    )
    await db.delete(dataset)
    await db.commit()
    await storage.delete_files([storage.dataset_name(dataset_id)])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
