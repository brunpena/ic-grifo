"""Armazenamento dos PDFs enviados: disco local ou Supabase Storage (`STORAGE_BACKEND`).

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


def _name(document_id: uuid.UUID) -> str:
    return f"{document_id}.pdf"


# ----- disco local -----


def _local_path(document_id: uuid.UUID) -> Path:
    return get_settings().local_storage_dir / _name(document_id)


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


async def save_pdf(document_id: uuid.UUID, data: bytes) -> str:
    if get_settings().storage_backend == "local":
        path = _local_path(document_id)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(write)
        return f"local:{_name(document_id)}"

    base, headers, bucket = _supabase()
    async with httpx.AsyncClient(timeout=60) as client:
        await _ensure_bucket(client)
        response = await client.post(
            f"{base}/object/{bucket}/{_name(document_id)}",
            headers={**headers, "Content-Type": "application/pdf", "x-upsert": "true"},
            content=data,
        )
    if response.status_code not in (200, 201):
        raise StorageError("Não foi possível salvar o arquivo no Supabase Storage.")
    return f"supabase:{bucket}/{_name(document_id)}"


async def read_pdf(document_id: uuid.UUID) -> bytes:
    if get_settings().storage_backend == "local":
        path = _local_path(document_id)
        if not path.exists():
            raise StorageError("Arquivo não encontrado.")
        return await asyncio.to_thread(path.read_bytes)

    base, headers, bucket = _supabase()
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(f"{base}/object/{bucket}/{_name(document_id)}", headers=headers)
    if response.status_code != 200:
        raise StorageError("Arquivo não encontrado.")
    return response.content


async def delete_pdf(document_id: uuid.UUID) -> None:
    if get_settings().storage_backend == "local":
        await asyncio.to_thread(_local_path(document_id).unlink, missing_ok=True)
        return
    base, headers, bucket = _supabase()
    async with httpx.AsyncClient(timeout=30) as client:
        await client.request(
            "DELETE",
            f"{base}/object/{bucket}",
            headers=headers,
            json={"prefixes": [_name(document_id)]},
        )
