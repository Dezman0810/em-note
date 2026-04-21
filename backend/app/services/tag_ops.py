"""Создание и поиск меток для владельца заметки (теги в БД привязаны к user_id владельца)."""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag
from app.utils.text import slugify


async def _unique_slug(
    db: AsyncSession, user_id: uuid.UUID, parent_id: uuid.UUID | None, base_slug: str
) -> str:
    slug = base_slug
    for _ in range(50):
        existing = await db.execute(
            select(Tag.id).where(
                Tag.user_id == user_id,
                Tag.parent_id == parent_id,
                Tag.slug == slug,
            )
        )
        if existing.scalar_one_or_none() is None:
            return slug
        slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="Could not allocate unique slug"
    )


async def _recompute_depths(db: AsyncSession, tag: Tag) -> None:
    if tag.parent_id is None:
        tag.depth = 1
    else:
        parent = await db.get(Tag, tag.parent_id)
        if parent is None or parent.user_id != tag.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid parent"
            )
        tag.depth = parent.depth + 1
    if tag.id is None:
        return
    children = await db.execute(select(Tag).where(Tag.parent_id == tag.id))
    for child in children.scalars().all():
        await _recompute_depths(db, child)


async def get_or_create_root_tag(db: AsyncSession, owner_id: uuid.UUID, raw_name: str) -> Tag:
    """Корневая метка (parent_id is None) по имени; без учёта регистра — одна сущность."""
    name = raw_name.strip()
    if not name or len(name) > 120:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tag name"
        )
    r = await db.execute(
        select(Tag).where(
            Tag.user_id == owner_id,
            Tag.parent_id.is_(None),
            func.lower(Tag.name) == name.lower(),
        )
    )
    existing = r.scalar_one_or_none()
    if existing:
        return existing
    tag = Tag(
        user_id=owner_id,
        parent_id=None,
        name=name,
        slug="",
        depth=1,
    )
    await _recompute_depths(db, tag)
    tag.slug = await _unique_slug(db, owner_id, tag.parent_id, slugify(tag.name))
    db.add(tag)
    await db.flush()
    await db.refresh(tag)
    return tag
