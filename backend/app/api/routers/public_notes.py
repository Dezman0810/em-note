from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.config import settings
from app.models.note import Note
from app.models.note_attachment import NoteAttachment
from app.models.note_public_link import NotePublicLink
from app.models.share import ShareRole
from app.schemas.attachment import AttachmentRead, TranscriptionRead
from app.services.audio_transcribe import transcribe_audio_file
from app.services.attachment_ops import create_attachment_for_note
from app.schemas.note import NoteRead, NoteUpdate
from app.schemas.public_link import PublicNotePayload
from app.utils.json_compare import json_doc_equal
from app.utils.text import plain_text_from_tiptap_json

router = APIRouter(prefix="/public", tags=["public-notes"])


async def _note_by_public_token(db: AsyncSession, token: str) -> tuple[Note, NotePublicLink]:
    result = await db.execute(
        select(NotePublicLink).where(NotePublicLink.token == token)
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found or revoked")
    n = await db.get(
        Note,
        link.note_id,
        options=(selectinload(Note.tags),),
    )
    if n is None or n.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return n, link


@router.get("/notes/{token}", response_model=PublicNotePayload)
async def get_public_note(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PublicNotePayload:
    note, link = await _note_by_public_token(db, token)
    can_edit = link.role == ShareRole.editor.value
    return PublicNotePayload(
        note=NoteRead.from_note_public(note),
        can_edit=can_edit,
        role=link.role,
    )


@router.patch("/notes/{token}", response_model=NoteRead)
async def patch_public_note(
    token: str,
    body: NoteUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NoteRead:
    note, link = await _note_by_public_token(db, token)
    if link.role != ShareRole.editor.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Edit not allowed for this link")
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return NoteRead.from_note_public(note)
    changed = False
    if "title" in updates and updates["title"] is not None and note.title != updates["title"]:
        note.title = updates["title"]
        changed = True
    if "content_json" in updates:
        new_cj = updates["content_json"]
        if not json_doc_equal(note.content_json, new_cj):
            note.content_json = new_cj
            changed = True
    if "content_plain" in updates:
        np = updates["content_plain"]
        if note.content_plain != np:
            note.content_plain = np
            changed = True
    elif "content_json" in updates:
        derived = plain_text_from_tiptap_json(note.content_json)
        if note.content_plain != derived:
            note.content_plain = derived
            changed = True
    if "folder_id" in updates and updates["folder_id"] is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot change folder via public link")
    if "accent_color" in updates and updates["accent_color"] is not None:
        ac = updates["accent_color"] or ""
        if (note.accent_color or "") != ac:
            note.accent_color = ac
            changed = True
    if changed:
        note.updated_at = datetime.now(timezone.utc)
        await db.flush()
    loaded = await db.get(
        Note,
        note.id,
        options=(selectinload(Note.tags),),
    )
    assert loaded is not None
    return NoteRead.from_note_public(loaded)


@router.post("/notes/{token}/attachments", response_model=AttachmentRead)
async def public_upload_attachment(
    token: str,
    file: Annotated[UploadFile, File()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AttachmentRead:
    note, link = await _note_by_public_token(db, token)
    if link.role != ShareRole.editor.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Edit not allowed for this link")
    row = await create_attachment_for_note(db, note.id, file)
    return AttachmentRead.from_row(row)


@router.post("/notes/{token}/attachments/{attachment_id}/transcribe", response_model=TranscriptionRead)
async def public_transcribe_attachment(
    token: str,
    attachment_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TranscriptionRead:
    note, link = await _note_by_public_token(db, token)
    if link.role != ShareRole.editor.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Edit not allowed for this link")
    row = await db.get(NoteAttachment, attachment_id)
    if row is None or row.note_id != note.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    path = Path(settings.attachments_dir) / row.storage_key
    text = await transcribe_audio_file(
        path,
        filename=row.original_filename or "audio.webm",
        content_type=row.content_type,
    )
    return TranscriptionRead(text=text)


@router.get("/notes/{token}/attachments/{attachment_id}/file")
async def public_download_attachment(
    token: str,
    attachment_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    note, _link = await _note_by_public_token(db, token)
    row = await db.get(NoteAttachment, attachment_id)
    if row is None or row.note_id != note.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    path = Path(settings.attachments_dir) / row.storage_key
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on disk")
    return FileResponse(
        path,
        media_type=row.content_type or "application/octet-stream",
        filename=row.original_filename or "download",
    )
