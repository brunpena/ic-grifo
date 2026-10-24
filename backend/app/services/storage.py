"""Armazenamento dos arquivos enviados (PDFs e CSVs): disco local ou Supabase Storage
(`STORAGE_BACKEND`).

No Supabase, o bucket (`SUPABASE_BUCKET`) é criado como privado no primeiro envio, se
ainda não existir. O acesso usa a chave service_role, que nunca vai para o front.
"""

import asyncio
import uuid
from pathlib import Path

import httpx

from app.core.config import get_settings


class StorageError(Exception):
    """Falha ao salvar ou ler o arquivo."""


def pdf_name(document_id: uuid.UUID) -> str:
    return f"{document_id}.pdf"


def dataset_name(dataset_id: uuid.UUID) -> str:
    return f"datasets/{dataset_id}.csv"


# ----- disco local -----


def _local_path(name: str) -> Path:
    return get_settings().local_storage_dir / name


# ----- Supabase Storage -----

_bucket_ready = False


def _supabase() -> tuple[str, dict[str, str], str]:
    settings = get_settings()
    key = settings.supabase_service_key.get_secret_value()
    if not settings.supabase_url or not key:
        raise StorageError("Configure SUPABASE_URL e SUPABASE_SERVICE_KEY no .env do back-end.")
    base = f"{settings.supabase_url.rstrip('/')}/storage/v1"
    return base, {"Authorization": f"Bearer {key}", "apikey": key}, settings.supabase_bucket


async def _ensure_bucket(client: httpx.AsyncClient) -> None:
    global _bucket_ready
    if _bucket_ready:
        return
    base, headers, bucket = _supabase()
    response = await client.get(f"{base}/bucket/{bucket}", headers=headers)
    if response.status_code != 200:
        created = await client.post(
            f"{base}/bucket",
            headers=headers,
            json={"id": bucket, "name": bucket, "public": False},
        )
        if created.status_code not in (200, 201, 409):
            raise StorageError(f"Não foi possível criar o bucket “{bucket}” no Supabase.")
    _bucket_ready = True


async def save_file(name: str, data: bytes, content_type: str) -> str:
    """Grava o arquivo e devolve o caminho para guardar no banco (`local:` ou `supabase:`)."""
    if get_settings().storage_backend == "local":
        path = _local_path(name)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(write)
        return f"local:{name}"

    base, headers, bucket = _supabase()
    async with httpx.AsyncClient(timeout=60) as client:
        await _ensure_bucket(client)
        response = await client.post(
            f"{base}/object/{bucket}/{name}",
            headers={**headers, "Content-Type": content_type, "x-upsert": "true"},
            content=data,
        )
    if response.status_code not in (200, 201):
        raise StorageError("Não foi possível salvar o arquivo no Supabase Storage.")
    return f"supabase:{bucket}/{name}"


async def read_file(name: str) -> bytes:
    if get_settings().storage_backend == "local":
        path = _local_path(name)
        if not path.exists():
            raise StorageError("Arquivo não encontrado.")
        return await asyncio.to_thread(path.read_bytes)

    base, headers, bucket = _supabase()
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(f"{base}/object/{bucket}/{name}", headers=headers)
    if response.status_code != 200:
        raise StorageError("Arquivo não encontrado.")
    return response.content


async def delete_files(names: list[str]) -> None:
    if not names:
        return
    if get_settings().storage_backend == "local":
        for name in names:
            await asyncio.to_thread(_local_path(name).unlink, missing_ok=True)
        return
    base, headers, bucket = _supabase()
    async with httpx.AsyncClient(timeout=30) as client:
        await client.request(
            "DELETE", f"{base}/object/{bucket}", headers=headers, json={"prefixes": names}
        )


# ----- atalhos para os PDFs dos documentos -----


async def save_pdf(document_id: uuid.UUID, data: bytes) -> str:
    return await save_file(pdf_name(document_id), data, "application/pdf")


async def read_pdf(document_id: uuid.UUID) -> bytes:
    return await read_file(pdf_name(document_id))


async def delete_pdf(document_id: uuid.UUID) -> None:
    await delete_files([pdf_name(document_id)])
