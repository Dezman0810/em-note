import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.note import Note
from app.models.note_public_link import NotePublicLink
from app.models.user import User
from app.schemas.public_link import NotePublicLinkRead, NotePublicLinkUpsert
from app.services.note_access import require_note_owner

router = APIRouter(tags=["note-public-links"])


def _new_token() -> str:
    return secrets.token_urlsafe(32)


@router.get("/notes/{note_id}/public-link", response_model=NotePublicLinkRead)
async def get_public_link(
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NotePublicLink:
    await require_note_owner(db, note_id, user.id)
    result = await db.execute(select(NotePublicLink).where(NotePublicLink.note_id == note_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public link not enabled")
    return row


@router.put("/notes/{note_id}/public-link", response_model=NotePublicLinkRead)
async def upsert_public_link(
    note_id: uuid.UUID,
    body: NotePublicLinkUpsert,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NotePublicLink:
    await require_note_owner(db, note_id, user.id)
    result = await db.execute(select(NotePublicLink).where(NotePublicLink.note_id == note_id))
    row = result.scalar_one_or_none()
    if row is None:
        row = NotePublicLink(note_id=note_id, token=_new_token(), role=body.role)
        db.add(row)
    else:
        row.role = body.role
    await db.flush()
    await db.refresh(row)
    return row


@router.post("/notes/{note_id}/public-link/regenerate", response_model=NotePublicLinkRead)
async def regenerate_public_link_token(
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NotePublicLink:
    await require_note_owner(db, note_id, user.id)
    result = await db.execute(select(NotePublicLink).where(NotePublicLink.note_id == note_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public link not enabled")
    row.token = _new_token()
    await db.flush()
    await db.refresh(row)
    return row


@router.delete("/notes/{note_id}/public-link", status_code=status.HTTP_204_NO_CONTENT)
async def delete_public_link(
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    await require_note_owner(db, note_id, user.id)
    result = await db.execute(select(NotePublicLink).where(NotePublicLink.note_id == note_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Public link not enabled")
    await db.delete(row)
