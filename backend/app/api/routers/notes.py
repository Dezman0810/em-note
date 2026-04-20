import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.folder import Folder
from app.models.note import Note
from app.models.note_tag import note_tag
from app.models.share import NoteShare
from app.models.tag import Tag
from app.models.user import User
from app.schemas.note import NoteCreate, NoteRead, NoteUpdate
from app.services.note_access import (
    get_note_for_read,
    require_note_edit,
    require_note_owner,
    require_trashed_note_owner,
)
from app.services.tag_subtree import subtree_tag_ids
from app.utils.json_compare import json_doc_equal
from app.utils.text import plain_text_from_tiptap_json

router = APIRouter(prefix="/notes", tags=["notes"])


async def _note_with_tags(db: AsyncSession, note_id: uuid.UUID) -> Note:
    result = await db.execute(
        select(Note).options(selectinload(Note.tags)).where(Note.id == note_id)
    )
    return result.scalar_one()


async def _validate_folder_for_owner(
    db: AsyncSession, folder_id: uuid.UUID | None, owner_id: uuid.UUID
) -> None:
    if folder_id is None:
        return
    folder = await db.get(Folder, folder_id)
    if folder is None or folder.user_id != owner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")


async def _validate_user_tag(db: AsyncSession, tag_id: uuid.UUID, user_id: uuid.UUID) -> None:
    tag = await db.get(Tag, tag_id)
    if tag is None or tag.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")


async def _user_tags_all(db: AsyncSession, user_id: uuid.UUID) -> list[Tag]:
    result = await db.execute(select(Tag).where(Tag.user_id == user_id))
    return list(result.scalars().all())


def _accessible_notes_query(user_id: uuid.UUID) -> Select[tuple[Note]]:
    shared_ids = select(NoteShare.note_id).where(NoteShare.shared_with_user_id == user_id)
    return (
        select(Note)
        .where(Note.deleted_at.is_(None))
        .where((Note.owner_id == user_id) | (Note.id.in_(shared_ids)))
        .order_by(Note.updated_at.desc())
        .options(selectinload(Note.tags))
    )


@router.get("/reminders", response_model=list[NoteRead])
async def list_reminders(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    from_: Annotated[datetime, Query(alias="from")],
    to: Annotated[datetime, Query()],
) -> list[NoteRead]:
    """Заметки с напоминанием в полуинтервале [from, to)."""
    if to <= from_:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="to must be after from"
        )
    shared_ids = select(NoteShare.note_id).where(NoteShare.shared_with_user_id == user.id)
    q = (
        select(Note)
        .where(Note.deleted_at.is_(None))
        .where((Note.owner_id == user.id) | (Note.id.in_(shared_ids)))
        .where(Note.reminder_at.is_not(None))
        .where(Note.reminder_at >= from_)
        .where(Note.reminder_at < to)
        .order_by(Note.reminder_at.asc())
        .options(selectinload(Note.tags))
    )
    result = await db.execute(q)
    notes = result.scalars().unique().all()
    return [NoteRead.from_note(n) for n in notes]


@router.get("", response_model=list[NoteRead])
async def list_notes(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    folder_id: Annotated[uuid.UUID | None, Query()] = None,
    unfoldered: Annotated[bool, Query()] = False,
    trash_only: Annotated[bool, Query()] = False,
    tag_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[NoteRead]:
    if trash_only:
        result = await db.execute(
            select(Note)
            .options(selectinload(Note.tags))
            .where(Note.owner_id == user.id, Note.deleted_at.is_not(None))
            .order_by(Note.deleted_at.desc())
        )
        trash_notes = result.scalars().unique().all()
        return [NoteRead.from_note(n) for n in trash_notes]

    if tag_id is not None:
        await _validate_user_tag(db, tag_id, user.id)

    q = _accessible_notes_query(user.id)
    if unfoldered:
        q = q.where(Note.folder_id.is_(None))
    elif folder_id is not None:
        folder = await db.get(Folder, folder_id)
        if folder is None or folder.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
        q = q.where(Note.folder_id == folder_id)
    if tag_id is not None:
        user_tags = await _user_tags_all(db, user.id)
        tree_ids = subtree_tag_ids(tag_id, user_tags)
        q = q.where(
            Note.id.in_(select(note_tag.c.note_id).where(note_tag.c.tag_id.in_(tree_ids)))
        )
    result = await db.execute(q)
    notes = result.scalars().unique().all()
    return [NoteRead.from_note(n) for n in notes]


def _ilike_pattern(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("/search", response_model=list[NoteRead])
async def search_notes(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    q: Annotated[str, Query(min_length=1, max_length=200)],
    folder_id: Annotated[uuid.UUID | None, Query()] = None,
    unfoldered: Annotated[bool, Query()] = False,
    tag_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[NoteRead]:
    if tag_id is not None:
        await _validate_user_tag(db, tag_id, user.id)

    pattern = _ilike_pattern(q)
    base = _accessible_notes_query(user.id).where(
        (Note.title.ilike(pattern, escape="\\")) | (Note.content_plain.ilike(pattern, escape="\\"))
    )
    if unfoldered:
        base = base.where(Note.folder_id.is_(None))
    elif folder_id is not None:
        folder = await db.get(Folder, folder_id)
        if folder is None or folder.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
        base = base.where(Note.folder_id == folder_id)
    if tag_id is not None:
        user_tags = await _user_tags_all(db, user.id)
        tree_ids = subtree_tag_ids(tag_id, user_tags)
        base = base.where(
            Note.id.in_(select(note_tag.c.note_id).where(note_tag.c.tag_id.in_(tree_ids)))
        )
    result = await db.execute(base)
    notes = result.scalars().unique().all()
    return [NoteRead.from_note(n) for n in notes]


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
async def create_note(
    body: NoteCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NoteRead:
    if not user.can_create_notes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Создание заметок отключено. Обратитесь к администратору.",
        )
    plain = body.content_plain
    if plain is None:
        plain = plain_text_from_tiptap_json(body.content_json)
    await _validate_folder_for_owner(db, body.folder_id, user.id)
    note = Note(
        owner_id=user.id,
        title=body.title,
        content_json=body.content_json,
        content_plain=plain,
        folder_id=body.folder_id,
        accent_color=body.accent_color or "",
        reminder_at=body.reminder_at,
    )
    db.add(note)
    await db.flush()
    loaded = await _note_with_tags(db, note.id)
    return NoteRead.from_note(loaded)


@router.get("/{note_id}", response_model=NoteRead)
async def get_note(
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NoteRead:
    await get_note_for_read(db, note_id, user.id)
    loaded = await _note_with_tags(db, note_id)
    return NoteRead.from_note(loaded)


@router.patch("/{note_id}", response_model=NoteRead)
async def update_note(
    note_id: uuid.UUID,
    body: NoteUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NoteRead:
    note = await require_note_edit(db, note_id, user.id)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        loaded = await _note_with_tags(db, note_id)
        return NoteRead.from_note(loaded)
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
    if "folder_id" in updates:
        fid = updates["folder_id"]
        if note.folder_id != fid:
            await _validate_folder_for_owner(db, fid, note.owner_id)
            note.folder_id = fid
            changed = True
    if "accent_color" in updates and updates["accent_color"] is not None:
        ac = updates["accent_color"] or ""
        if (note.accent_color or "") != ac:
            note.accent_color = ac
            changed = True
    if "reminder_at" in updates and note.reminder_at != updates["reminder_at"]:
        note.reminder_at = updates["reminder_at"]
        changed = True
    if changed:
        note.updated_at = datetime.now(timezone.utc)
        await db.flush()
    loaded = await _note_with_tags(db, note_id)
    return NoteRead.from_note(loaded)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    note = await require_note_owner(db, note_id, user.id)
    note.deleted_at = datetime.now(timezone.utc)


@router.post("/{note_id}/restore", response_model=NoteRead)
async def restore_note(
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NoteRead:
    note = await require_trashed_note_owner(db, note_id, user.id)
    note.deleted_at = None
    await db.flush()
    loaded = await _note_with_tags(db, note_id)
    return NoteRead.from_note(loaded)


@router.delete("/{note_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def purge_note(
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    note = await require_trashed_note_owner(db, note_id, user.id)
    await db.delete(note)


@router.post("/{note_id}/tags/{tag_id}", response_model=NoteRead)
async def attach_tag(
    note_id: uuid.UUID,
    tag_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NoteRead:
    from app.models.tag import Tag

    note = await require_note_edit(db, note_id, user.id)
    tag_result = await db.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == note.owner_id))
    tag = tag_result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
    if tag not in note.tags:
        note.tags.append(tag)
        note.updated_at = datetime.now(timezone.utc)
    await db.flush()
    loaded = await _note_with_tags(db, note_id)
    return NoteRead.from_note(loaded)


@router.delete("/{note_id}/tags/{tag_id}", response_model=NoteRead)
async def detach_tag(
    note_id: uuid.UUID,
    tag_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NoteRead:
    note = await require_note_edit(db, note_id, user.id)
    before = len(note.tags)
    note.tags = [t for t in note.tags if t.id != tag_id]
    if len(note.tags) < before:
        note.updated_at = datetime.now(timezone.utc)
    await db.flush()
    loaded = await _note_with_tags(db, note_id)
    return NoteRead.from_note(loaded)
