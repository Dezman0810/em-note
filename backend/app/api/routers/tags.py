import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.folder import Folder
from app.models.note import Note
from app.models.note_tag import note_tag
from app.models.share import NoteShare
from app.models.tag import Tag
from app.models.user import User
from app.schemas.tag import TagCreate, TagNoteCountRead, TagRead, TagUpdate
from app.services.tag_subtree import subtree_tag_ids
from app.utils.text import slugify

router = APIRouter(prefix="/tags", tags=["tags"])


async def _assert_tag_ownership(db: AsyncSession, tag_id: uuid.UUID, user_id: uuid.UUID) -> Tag:
    result = await db.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id))
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    return tag


async def _tag_name_taken(
    db: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    *,
    exclude_tag_id: uuid.UUID | None,
) -> bool:
    """Дубликат имени среди всех меток пользователя (без учёта регистра)."""
    norm = name.strip()
    if not norm:
        return False
    stmt = select(Tag.id).where(
        Tag.user_id == user_id,
        func.lower(Tag.name) == norm.lower(),
    )
    if exclude_tag_id is not None:
        stmt = stmt.where(Tag.id != exclude_tag_id)
    return (await db.execute(stmt)).scalar_one_or_none() is not None


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
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Could not allocate unique slug")


async def _recompute_depths(db: AsyncSession, tag: Tag) -> None:
    if tag.parent_id is None:
        tag.depth = 1
    else:
        parent = await db.get(Tag, tag.parent_id)
        if parent is None or parent.user_id != tag.user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid parent")
        tag.depth = parent.depth + 1
    if tag.id is None:
        return
    children = await db.execute(select(Tag).where(Tag.parent_id == tag.id))
    for child in children.scalars().all():
        await _recompute_depths(db, child)


async def _would_create_cycle(db: AsyncSession, tag: Tag, new_parent_id: uuid.UUID) -> bool:
    current_id: uuid.UUID | None = new_parent_id
    while current_id is not None:
        if current_id == tag.id:
            return True
        parent = await db.get(Tag, current_id)
        if parent is None:
            return False
        current_id = parent.parent_id
    return False


def _accessible_note_ids_stmt(
    user_id: uuid.UUID, folder_ids: list[uuid.UUID] | None, unfoldered: bool
) -> Select[tuple[uuid.UUID]]:
    shared_ids = select(NoteShare.note_id).where(NoteShare.shared_with_user_id == user_id)
    stmt = (
        select(Note.id)
        .where(Note.deleted_at.is_(None))
        .where((Note.owner_id == user_id) | (Note.id.in_(shared_ids)))
    )
    if unfoldered:
        stmt = stmt.where(Note.folder_id.is_(None))
    elif folder_ids:
        stmt = stmt.where(Note.folder_id.in_(folder_ids))
    return stmt


@router.get("/counts", response_model=list[TagNoteCountRead])
@router.get("/note-counts", response_model=list[TagNoteCountRead], include_in_schema=False)
async def tag_note_counts(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    folder_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    unfoldered: Annotated[bool, Query()] = False,
) -> list[TagNoteCountRead]:
    raw = folder_id or []
    if unfoldered:
        scope_folder_ids: list[uuid.UUID] | None = None
    elif raw:
        for fid in raw:
            folder = await db.get(Folder, fid)
            if folder is None or folder.user_id != user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
        scope_folder_ids = raw
    else:
        scope_folder_ids = None

    scope = _accessible_note_ids_stmt(user.id, scope_folder_ids, unfoldered)
    tags_result = await db.execute(select(Tag).where(Tag.user_id == user.id))
    user_tags = list(tags_result.scalars().all())
    user_tags.sort(key=lambda t: (t.depth, t.name))
    note_scope_sq = scope.subquery()
    out: list[TagNoteCountRead] = []
    for tag in user_tags:
        tree_ids = subtree_tag_ids(tag.id, user_tags)
        if not tree_ids:
            out.append(TagNoteCountRead(tag_id=tag.id, count=0))
            continue
        cnt_stmt = (
            select(func.count(func.distinct(note_tag.c.note_id)))
            .select_from(note_tag)
            .where(
                note_tag.c.note_id.in_(select(note_scope_sq.c.id)),
                note_tag.c.tag_id.in_(tree_ids),
            )
        )
        raw = (await db.execute(cnt_stmt)).scalar_one()
        out.append(TagNoteCountRead(tag_id=tag.id, count=int(raw)))
    return out


@router.get("", response_model=list[TagRead])
async def list_tags(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[Tag]:
    result = await db.execute(
        select(Tag).where(Tag.user_id == user.id).order_by(Tag.depth, Tag.name)
    )
    return list(result.scalars().all())


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(
    body: TagCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Tag:
    name_stripped = body.name.strip()
    if not name_stripped or len(name_stripped) > 120:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректное имя метки",
        )
    if body.parent_id is not None:
        await _assert_tag_ownership(db, body.parent_id, user.id)
    if await _tag_name_taken(db, user.id, name_stripped, exclude_tag_id=None):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Метка с таким именем уже существует",
        )
    tag = Tag(
        user_id=user.id,
        parent_id=body.parent_id,
        name=name_stripped,
        slug="",
        depth=1,
    )
    await _recompute_depths(db, tag)
    tag.slug = await _unique_slug(db, user.id, tag.parent_id, slugify(tag.name))
    db.add(tag)
    await db.flush()
    await db.refresh(tag)
    return tag


@router.patch("/{tag_id}", response_model=TagRead)
async def update_tag(
    tag_id: uuid.UUID,
    body: TagUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Tag:
    tag = await _assert_tag_ownership(db, tag_id, user.id)
    updates: dict[str, Any] = body.model_dump(exclude_unset=True)

    if "parent_id" in updates:
        new_parent: uuid.UUID | None = updates["parent_id"]
        if new_parent == tag.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot set parent to self")
        if new_parent is not None:
            await _assert_tag_ownership(db, new_parent, user.id)
            if await _would_create_cycle(db, tag, new_parent):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cycle detected")
        tag.parent_id = new_parent
        await _recompute_depths(db, tag)

    if "name" in updates and updates["name"] is not None:
        nm = updates["name"].strip()
        if not nm or len(nm) > 120:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Некорректное имя метки",
            )
        tag.name = nm

    if "parent_id" in updates or ("name" in updates and updates["name"] is not None):
        if await _tag_name_taken(db, user.id, tag.name, exclude_tag_id=tag.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Метка с таким именем уже существует",
            )
        tag.slug = await _unique_slug(db, user.id, tag.parent_id, slugify(tag.name))

    await db.flush()
    await db.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    tag = await _assert_tag_ownership(db, tag_id, user.id)
    children_result = await db.execute(select(Tag).where(Tag.parent_id == tag.id))
    promote_to = tag.parent_id
    for child in children_result.scalars().all():
        child.parent_id = promote_to
        await _recompute_depths(db, child)
        if await _tag_name_taken(db, user.id, child.name, exclude_tag_id=child.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя удалить: метка с таким именем уже есть. Переименуйте потомка.",
            )
        child.slug = await _unique_slug(db, user.id, child.parent_id, slugify(child.name))
    await db.flush()
    await db.delete(tag)
