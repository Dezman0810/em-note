import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.note_attachment import NoteAttachment
from app.models.user import User
from app.schemas.attachment import AttachmentRead
from app.services.attachment_ops import create_attachment_for_note
from app.services.note_access import get_note_for_read, require_note_edit

router = APIRouter(tags=["attachments"])


@router.post("/notes/{note_id}/attachments", response_model=AttachmentRead)
async def upload_attachment(
    note_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AttachmentRead:
    await require_note_edit(db, note_id, user.id)
    row = await create_attachment_for_note(db, note_id, file)
    return AttachmentRead.from_row(row)


@router.get("/attachments/{attachment_id}/file")
async def download_attachment(
    attachment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    row = await db.get(NoteAttachment, attachment_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    await get_note_for_read(db, row.note_id, user.id)
    path = Path(settings.attachments_dir) / row.storage_key
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")
    return FileResponse(
        path,
        media_type=row.content_type or "application/octet-stream",
        filename=row.original_filename or "download",
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    row = await db.get(NoteAttachment, attachment_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    await require_note_edit(db, row.note_id, user.id)
    path = Path(settings.attachments_dir) / row.storage_key
    await db.delete(row)
    await db.flush()
    path.unlink(missing_ok=True)
