import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, Uuid, column, func, select, values
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.note import Note
from app.models.note_tag import note_tag
from app.models.note_user_personal_tag import note_user_personal_tag
from app.models.share import NoteShare
from app.models.tag import Tag
from app.models.user import User
from app.schemas.tag import TagCreate, TagNoteCountRead, TagRead, TagUpdate
from app.services.folder_access import assert_folders_owned
from app.services.note_personal_view import folder_exclude_predicate, folder_scope_predicate
from app.services.tag_ops import recompute_depths, unique_slug
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
    """Р”СѓР±Р»РёРєР°С‚ РёРјРµРЅРё СЃСЂРµРґРё РІСЃРµС… РјРµС‚РѕРє РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ (Р±РµР· СѓС‡С‘С‚Р° СЂРµРіРёСЃС‚СЂР°)."""
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
    user_id: uuid.UUID,
    folder_ids: list[uuid.UUID] | None,
    unfoldered: bool,
    exclude_folder_ids: list[uuid.UUID] | None = None,
) -> Select[tuple[uuid.UUID]]:
    shared_ids = select(NoteShare.note_id).where(NoteShare.shared_with_user_id == user_id)
    stmt = (
        select(Note.id)
        .where(Note.deleted_at.is_(None))
        .where((Note.owner_id == user_id) | (Note.id.in_(shared_ids)))
    )
    if unfoldered or folder_ids:
        stmt = stmt.where(folder_scope_predicate(user_id, None if unfoldered else folder_ids, unfoldered))
    if exclude_folder_ids:
        stmt = stmt.where(~folder_exclude_predicate(user_id, exclude_folder_ids))
    return stmt


@router.get("/counts", response_model=list[TagNoteCountRead])
@router.get("/note-counts", response_model=list[TagNoteCountRead], include_in_schema=False)
async def tag_note_counts(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    folder_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    unfoldered: Annotated[bool, Query()] = False,
    exclude_folder_id: Annotated[list[uuid.UUID] | None, Query()] = None,
) -> list[TagNoteCountRead]:
    raw = folder_id or []
    exclude_raw = exclude_folder_id or []
    await assert_folders_owned(db, exclude_raw, user.id)
    if unfoldered:
        scope_folder_ids: list[uuid.UUID] | None = None
    elif raw:
        await assert_folders_owned(db, raw, user.id)
        scope_folder_ids = raw
    else:
        scope_folder_ids = None

    scope = _accessible_note_ids_stmt(
        user.id, scope_folder_ids, unfoldered, exclude_raw if exclude_raw else None
    )
    tags_result = await db.execute(select(Tag).where(Tag.user_id == user.id))
    user_tags = list(tags_result.scalars().all())
    user_tags.sort(key=lambda t: (t.depth, t.name))
    if not user_tags:
        return []

    counts = await _subtree_note_counts(db, user.id, user_tags, scope)
    return [TagNoteCountRead(tag_id=t.id, count=counts.get(t.id, 0)) for t in user_tags]


async def _subtree_note_counts(
    db: AsyncSession,
    user_id: uuid.UUID,
    user_tags: list[Tag],
    scope: Select[tuple[uuid.UUID]],
) -> dict[uuid.UUID, int]:
    """РћРґРЅРёРј GROUP BY: РґР»СЏ РєР°Р¶РґРѕР№ РјРµС‚РєРё вЂ” С‡РёСЃР»Рѕ Р·Р°РјРµС‚РѕРє РёР· scope РІ РµС‘ РїРѕРґРґРµСЂРµРІРµ.

    РњРµС‚РєР° В«РІРёСЃРёС‚В» РЅР° Р·Р°РјРµС‚РєРµ Р»РёР±Рѕ РєР°РЅРѕРЅРёС‡РµСЃРєРё (note_tags, С‚РѕР»СЊРєРѕ СЃРІРѕРё Р·Р°РјРµС‚РєРё),
    Р»РёР±Рѕ Р»РёС‡РЅРѕ Сѓ РїРѕР»СѓС‡Р°С‚РµР»СЏ С€Р°СЂРёРЅРіР° (note_user_personal_tags) вЂ” РєР°Рє РІ С„РёР»СЊС‚СЂР°С… СЃРїРёСЃРєР°.
    РџРѕРґРґРµСЂРµРІСЊСЏ СЂР°СЃРєСЂС‹РІР°СЋС‚СЃСЏ РІ VALUES-С‚Р°Р±Р»РёС†Сѓ (ancestor, descendant).
    """
    scope_ids = select(scope.subquery().c.id)
    canonical = select(
        note_tag.c.tag_id.label("tag_id"), note_tag.c.note_id.label("note_id")
    ).where(
        note_tag.c.note_id.in_(scope_ids),
        note_tag.c.note_id.in_(select(Note.id).where(Note.owner_id == user_id)),
    )
    personal = select(
        note_user_personal_tag.c.tag_id.label("tag_id"),
        note_user_personal_tag.c.note_id.label("note_id"),
    ).where(
        note_user_personal_tag.c.user_id == user_id,
        note_user_personal_tag.c.note_id.in_(scope_ids),
    )
    direct = canonical.union(personal).subquery("direct_tag_notes")

    pairs = [(t.id, d) for t in user_tags for d in subtree_tag_ids(t.id, user_tags)]
    tree = values(
        column("ancestor", Uuid(as_uuid=True)),
        column("descendant", Uuid(as_uuid=True)),
        name="tag_tree",
    ).data(pairs)

    rows = (
        await db.execute(
            select(tree.c.ancestor, func.count(func.distinct(direct.c.note_id)))
            .select_from(
                tree.outerjoin(direct, direct.c.tag_id == tree.c.descendant)
            )
            .group_by(tree.c.ancestor)
        )
    ).all()
    return {tag_id: int(cnt) for tag_id, cnt in rows}


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
            detail="РќРµРєРѕСЂСЂРµРєС‚РЅРѕРµ РёРјСЏ РјРµС‚РєРё",
        )
    if body.parent_id is not None:
        await _assert_tag_ownership(db, body.parent_id, user.id)
    if await _tag_name_taken(db, user.id, name_stripped, exclude_tag_id=None):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="РњРµС‚РєР° СЃ С‚Р°РєРёРј РёРјРµРЅРµРј СѓР¶Рµ СЃСѓС‰РµСЃС‚РІСѓРµС‚",
        )
    tag = Tag(
        user_id=user.id,
        parent_id=body.parent_id,
        name=name_stripped,
        slug="",
        depth=1,
    )
    await recompute_depths(db, tag)
    tag.slug = await unique_slug(db, user.id, tag.parent_id, slugify(tag.name))
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
        await recompute_depths(db, tag)

    if "name" in updates and updates["name"] is not None:
        nm = updates["name"].strip()
        if not nm or len(nm) > 120:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="РќРµРєРѕСЂСЂРµРєС‚РЅРѕРµ РёРјСЏ РјРµС‚РєРё",
            )
        tag.name = nm

    if "parent_id" in updates or ("name" in updates and updates["name"] is not None):
        if await _tag_name_taken(db, user.id, tag.name, exclude_tag_id=tag.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="РњРµС‚РєР° СЃ С‚Р°РєРёРј РёРјРµРЅРµРј СѓР¶Рµ СЃСѓС‰РµСЃС‚РІСѓРµС‚",
            )
        tag.slug = await unique_slug(db, user.id, tag.parent_id, slugify(tag.name))

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
        await recompute_depths(db, child)
        if await _tag_name_taken(db, user.id, child.name, exclude_tag_id=child.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="РќРµР»СЊР·СЏ СѓРґР°Р»РёС‚СЊ: РјРµС‚РєР° СЃ С‚Р°РєРёРј РёРјРµРЅРµРј СѓР¶Рµ РµСЃС‚СЊ. РџРµСЂРµРёРјРµРЅСѓР№С‚Рµ РїРѕС‚РѕРјРєР°.",
            )
        child.slug = await unique_slug(db, user.id, child.parent_id, slugify(child.name))
    await db.flush()
    await db.delete(tag)
