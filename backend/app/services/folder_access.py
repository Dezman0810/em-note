"""Проверка принадлежности папок пользователю (одним запросом на список)."""

import uuid
from collections.abc import Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.folder import Folder


async def assert_folders_owned(
    db: AsyncSession, folder_ids: Sequence[uuid.UUID], user_id: uuid.UUID
) -> None:
    """404, если хотя бы одна папка не существует или принадлежит другому пользователю."""
    wanted = {fid for fid in folder_ids}
    if not wanted:
        return
    found = set(
        (
            await db.execute(
                select(Folder.id).where(Folder.user_id == user_id, Folder.id.in_(wanted))
            )
        )
        .scalars()
        .all()
    )
    if found != wanted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
