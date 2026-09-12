import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.note_attachment import NoteAttachment
from app.models.user import User
from app.schemas.attachment import AttachmentRead, TranscriptionRead
from app.services.audio_transcribe import transcribe_audio_file
from app.services.attachment_ops import (
    attachment_file_exists,
    attachment_file_response,
    create_attachment_for_note,
    remove_attachment_file,
)
from app.services.note_access import get_note_access, require_note_edit

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


@router.post("/attachments/{attachment_id}/transcribe", response_model=TranscriptionRead)
async def transcribe_attachment(
    attachment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> TranscriptionRead:
    row = await db.get(NoteAttachment, attachment_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    await require_note_edit(db, row.note_id, user.id)
    path = Path(settings.attachments_dir) / row.storage_key
    text = await transcribe_audio_file(
        path,
        filename=row.original_filename or "audio.webm",
        content_type=row.content_type,
    )
    return TranscriptionRead(text=text)


@router.get("/attachments/{attachment_id}/file")
async def download_attachment(
    attachment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
):
    row = await db.get(NoteAttachment, attachment_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    await get_note_access(db, row.note_id, user.id)
    path = Path(settings.attachments_dir) / row.storage_key
    if not await attachment_file_exists(path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")
    return attachment_file_response(row, path, if_none_match)


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
    await remove_attachment_file(path)
