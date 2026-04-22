import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.note_attachment import NoteAttachment

_MAX_READ_CHUNK = 1024 * 1024


def ensure_attachments_dir() -> Path:
    p = Path(settings.attachments_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


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

    base_dir = ensure_attachments_dir()
    storage_key = str(uuid.uuid4())
    dest = base_dir / storage_key

    total = 0
    try:
        with dest.open("wb") as out:
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
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except OSError:
        dest.unlink(missing_ok=True)
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
