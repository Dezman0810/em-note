import asyncio
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.note_attachment import NoteAttachment
from app.utils.http_cache import IMMUTABLE_CACHE_CONTROL, etag_matches, make_etag

_MAX_READ_CHUNK = 1024 * 1024


def _ensure_attachments_dir_blocking() -> Path:
    p = Path(settings.attachments_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


async def ensure_attachments_dir() -> Path:
    return await asyncio.to_thread(_ensure_attachments_dir_blocking)


async def remove_attachment_file(path: Path) -> None:
    """Удаление файла с диска вне event loop."""
    await asyncio.to_thread(path.unlink, missing_ok=True)


async def attachment_file_exists(path: Path) -> bool:
    return await asyncio.to_thread(path.is_file)


def attachment_file_response(
    row: NoteAttachment, path: Path, if_none_match: str | None
) -> Response:
    """Отдача файла с длинным кешем и 304 по If-None-Match.

    Содержимое вложения неизменяемо: storage_key уникален, файл не перезаписывается.
    """
    etag = make_etag(row.id, row.storage_key, row.size_bytes, row.created_at)
    headers = {"Cache-Control": IMMUTABLE_CACHE_CONTROL, "ETag": etag}
    if etag_matches(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return FileResponse(
        path,
        media_type=row.content_type or "application/octet-stream",
        filename=row.original_filename or "download",
        headers=headers,
    )


def safe_attachment_filename(name: str) -> str:
    base = (name or "file").replace("\x00", "").strip()
    if not base:
        base = "file"
    base = Path(base).name
    return base[:500] if len(base) > 500 else base


async def create_attachment_for_note(
    db: AsyncSession,
    note_id: uuid.UUID,
    file: UploadFile,
) -> NoteAttachment:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename")

    base_dir = await ensure_attachments_dir()
    storage_key = str(uuid.uuid4())
    dest = base_dir / storage_key

    total = 0
    try:
        # open/write/close — блокирующие вызовы, каждый уходит в поток.
        handle = await asyncio.to_thread(dest.open, "wb")
        try:
            while True:
                chunk = await file.read(_MAX_READ_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_attachment_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File too large",
                    )
                await asyncio.to_thread(handle.write, chunk)
        finally:
            await asyncio.to_thread(handle.close)
    except HTTPException:
        await remove_attachment_file(dest)
        raise
    except OSError:
        await remove_attachment_file(dest)
        raise HTTPException(status_code=500, detail="Failed to save file")

    content_type = file.content_type or "application/octet-stream"
    row = NoteAttachment(
        note_id=note_id,
        storage_key=storage_key,
        original_filename=safe_attachment_filename(file.filename),
        content_type=content_type[:250],
        size_bytes=total,
    )
    db.add(row)
    await db.flush()
    return row
