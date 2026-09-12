import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_current_user, get_db
from app.models.folder import Folder
from app.models.note import Note
from app.models.share import NoteShare
from app.models.note_user_placement import NoteUserPlacement
from app.models.user import User
from app.schemas.folder import (
    FolderCreate,
    FolderCountItem,
    FolderNoteCountsRead,
    FolderRead,
    FolderUpdate,
)
from app.services.note_access import get_note_access

router = APIRouter(prefix="/folders", tags=["folders"])


def _accessible_notes_filter(user_id: uuid.UUID):
    shared_ids = select(NoteShare.note_id).where(NoteShare.shared_with_user_id == user_id)
    return Note.deleted_at.is_(None) & (
        (Note.owner_id == user_id) | (Note.id.in_(shared_ids))
    )


@router.get("/note-counts", response_model=FolderNoteCountsRead)
async def folder_note_counts(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> FolderNoteCountsRead:
    cond = _accessible_notes_filter(user.id)
    # Одним GROUP BY: «эффективная» папка — своя folder_id у владельца, личное
    # размещение у получателя шаринга (uq_note_user_placement — не более одной строки).
    placement = aliased(NoteUserPlacement)
    effective_folder = case(
        (Note.owner_id == user.id, Note.folder_id),
        else_=placement.folder_id,
    ).label("effective_folder_id")
    grouped = (
        await db.execute(
            select(effective_folder, func.count(Note.id))
            .select_from(Note)
            .outerjoin(
                placement,
                (placement.note_id == Note.id) & (placement.user_id == user.id),
            )
            .where(cond)
            .group_by(effective_folder)
        )
    ).all()
    by_folder = {fid: int(cnt) for fid, cnt in grouped}

    folders_result = await db.execute(
        select(Folder.id).where(Folder.user_id == user.id).order_by(Folder.name)
    )
    folder_counts = [
        FolderCountItem(folder_id=fid, count=by_folder.get(fid, 0))
        for fid in folders_result.scalars().all()
    ]

    return FolderNoteCountsRead(
        total=sum(by_folder.values()),
        unfoldered=by_folder.get(None, 0),
        folder_counts=folder_counts,
    )


async def _get_owned_folder(
    db: AsyncSession, folder_id: uuid.UUID, user_id: uuid.UUID
) -> Folder:
    folder = await db.get(Folder, folder_id)
    if folder is None or folder.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    return folder


@router.get("", response_model=list[FolderRead])
async def list_folders(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    for_note_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[Folder]:
    if for_note_id is not None:
        await get_note_access(db, for_note_id, user.id)
        result = await db.execute(
            select(Folder).where(Folder.user_id == user.id).order_by(Folder.name)
        )
        return list(result.scalars().all())
    result = await db.execute(select(Folder).where(Folder.user_id == user.id).order_by(Folder.name))
    return list(result.scalars().all())


@router.post("", response_model=FolderRead, status_code=status.HTTP_201_CREATED)
async def create_folder(
    body: FolderCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Folder:
    name = body.name.strip()
    dup = await db.execute(
        select(Folder.id).where(Folder.user_id == user.id, Folder.name == name)
    )
    if dup.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Folder already exists")
    folder = Folder(user_id=user.id, name=name)
    db.add(folder)
    await db.flush()
    await db.refresh(folder)
    return folder


@router.patch("/{folder_id}", response_model=FolderRead)
async def update_folder(
    folder_id: uuid.UUID,
    body: FolderUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Folder:
    folder = await _get_owned_folder(db, folder_id, user.id)
    if body.name is not None:
        name = body.name.strip()
        dup = await db.execute(
            select(Folder.id).where(
                Folder.user_id == user.id, Folder.name == name, Folder.id != folder.id
            )
        )
        if dup.scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Folder already exists")
        folder.name = name
    await db.flush()
    await db.refresh(folder)
    return folder


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    folder = await _get_owned_folder(db, folder_id, user.id)
    await db.delete(folder)
