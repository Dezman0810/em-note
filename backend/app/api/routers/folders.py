import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.folder import Folder
from app.models.user import User
from app.schemas.folder import FolderCreate, FolderRead, FolderUpdate
from app.services.note_access import get_note_for_read

router = APIRouter(prefix="/folders", tags=["folders"])


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
        note, _ = await get_note_for_read(db, for_note_id, user.id)
        result = await db.execute(
            select(Folder).where(Folder.user_id == note.owner_id).order_by(Folder.name)
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
