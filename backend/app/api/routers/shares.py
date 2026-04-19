import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.share import NoteShare
from app.models.user import User
from app.schemas.share import NoteShareCreate, NoteShareRead
from app.services.note_access import require_note_owner

router = APIRouter(tags=["shares"])


@router.get("/notes/{note_id}/shares", response_model=list[NoteShareRead])
async def list_note_shares(
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[NoteShare]:
    await require_note_owner(db, note_id, user.id)
    result = await db.execute(select(NoteShare).where(NoteShare.note_id == note_id))
    return list(result.scalars().all())


@router.post("/notes/{note_id}/shares", response_model=NoteShareRead, status_code=status.HTTP_201_CREATED)
async def create_note_share(
    note_id: uuid.UUID,
    body: NoteShareCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NoteShare:
    await require_note_owner(db, note_id, user.id)
    shared_with: uuid.UUID | None = body.shared_with_user_id
    invite_email: str | None = body.invite_email.lower() if body.invite_email else None

    if shared_with is not None:
        if shared_with == user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot share with yourself")
        target = await db.get(User, shared_with)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    elif invite_email is not None:
        result = await db.execute(select(User).where(User.email == invite_email))
        found = result.scalar_one_or_none()
        shared_with = found.id if found else None

    dup_stmt = select(NoteShare.id).where(NoteShare.note_id == note_id)
    if shared_with is not None:
        dup_stmt = dup_stmt.where(NoteShare.shared_with_user_id == shared_with)
    else:
        dup_stmt = dup_stmt.where(NoteShare.invite_email == invite_email)
    dup = await db.execute(dup_stmt)
    if dup.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Share already exists")

    share = NoteShare(
        note_id=note_id,
        shared_with_user_id=shared_with,
        invite_email=invite_email if shared_with is None else None,
        role=body.role,
    )
    db.add(share)
    await db.flush()
    await db.refresh(share)
    return share


@router.delete("/notes/{note_id}/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note_share(
    note_id: uuid.UUID,
    share_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    await require_note_owner(db, note_id, user.id)
    share = await db.get(NoteShare, share_id)
    if share is None or share.note_id != note_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")
    await db.delete(share)
