import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, require_admin
from app.models.note import Note
from app.models.share import NoteShare, ShareRole
from app.models.tag import Tag
from app.models.user import User
from app.schemas.note import NoteCreate, NoteRead, NoteUpdate, TagAttachByNameResult
from app.schemas.tag import TagAttachByName, TagRead
from app.services.folder_access import assert_folders_owned
from app.services.note_access import (
    Access,
    ensure_note_editable,
    get_note_access,
    require_note_owner,
    require_trashed_note_owner,
)
from app.services.note_ownership import take_note_ownership
from app.services.note_personal_view import (
    add_personal_tag_link,
    has_personal_tag,
    note_read_overlay,
    personal_tag_ids_map,
    placement_folder_map,
    remove_personal_tag_link,
    upsert_placement,
)
from app.services.note_query import (
    LIST_LOAD_OPTIONS,
    NoteListFilters,
    build_note_list_query,
)
from app.services.note_search import note_search_predicate
from app.services.tag_ops import get_or_create_root_tag
from app.utils.json_compare import json_doc_equal
from app.utils.text import plain_text_from_tiptap_json

router = APIRouter(prefix="/notes", tags=["notes"])


def _note_read_with_access(note: Note, access: Access, *, for_list: bool = False) -> NoteRead:
    """Только когда не нужна персональная подстановка папки/меток."""
    base = NoteRead.from_note_for_list(note) if for_list else NoteRead.from_note(note)
    return base.model_copy(update={"my_access": access.value})


async def _access_map_for_note_list(
    db: AsyncSession, user_id: uuid.UUID, notes: list[Note]
) -> dict[uuid.UUID, Access]:
    """Для списков: владелец — owner; по шеру — edit или read."""
    out: dict[uuid.UUID, Access] = {}
    shared_ids: list[uuid.UUID] = []
    for n in notes:
        if n.owner_id == user_id:
            out[n.id] = Access.owner
        else:
            shared_ids.append(n.id)
    if not shared_ids:
        return out
    rows = (
        await db.execute(
            select(NoteShare.note_id, NoteShare.role).where(
                NoteShare.shared_with_user_id == user_id,
                NoteShare.note_id.in_(shared_ids),
            )
        )
    ).all()
    role_by_note = {nid: role for nid, role in rows}
    for nid in shared_ids:
        role = role_by_note.get(nid)
        out[nid] = Access.edit if role == ShareRole.editor.value else Access.read
    return out


async def _notes_to_read_models(
    db: AsyncSession,
    user_id: uuid.UUID,
    notes: list[Note],
    *,
    for_list: bool = False,
) -> list[NoteRead]:
    acc_map = await _access_map_for_note_list(db, user_id, notes)
    shared_nid = [n.id for n in notes if n.owner_id != user_id]
    pmap = await placement_folder_map(db, user_id, shared_nid)
    tmap = await personal_tag_ids_map(db, user_id, shared_nid)
    out: list[NoteRead] = []
    for n in notes:
        acc = acc_map[n.id]
        if n.owner_id == user_id:
            out.append(_note_read_with_access(n, acc, for_list=for_list))
        else:
            out.append(
                note_read_overlay(
                    n,
                    acc,
                    viewer_id=user_id,
                    folder_effective=pmap.get(n.id),
                    tag_ids_effective=tmap.get(n.id, []),
                    for_list=for_list,
                )
            )
    return out


async def _note_with_tags(db: AsyncSession, note_id: uuid.UUID) -> Note:
    result = await db.execute(
        select(Note).options(selectinload(Note.tags)).where(Note.id == note_id)
    )
    return result.scalar_one()


async def note_read_for_requester(
    db: AsyncSession, user_id: uuid.UUID, note: Note, access: Access
) -> NoteRead:
    """Полное представление уже загруженной заметки (метки приходят из get_note_access)."""
    if note.owner_id == user_id:
        return _note_read_with_access(note, access)
    pmap = await placement_folder_map(db, user_id, [note.id])
    tmap = await personal_tag_ids_map(db, user_id, [note.id])
    return note_read_overlay(
        note,
        access,
        viewer_id=user_id,
        folder_effective=pmap.get(note.id),
        tag_ids_effective=tmap.get(note.id, []),
    )


async def _validate_folder_for_owner(
    db: AsyncSession, folder_id: uuid.UUID | None, owner_id: uuid.UUID
) -> None:
    if folder_id is None:
        return
    await assert_folders_owned(db, [folder_id], owner_id)


def _filters_from_query(
    folder_id: list[uuid.UUID] | None,
    unfoldered: bool,
    tag_id: list[uuid.UUID] | None,
    conjunct_tag_id: list[uuid.UUID] | None,
    exclude_tag_id: list[uuid.UUID] | None,
    exclude_tag_undo_id: list[uuid.UUID] | None,
    exclude_folder_id: list[uuid.UUID] | None,
    tag_match_all: bool,
) -> NoteListFilters:
    return NoteListFilters(
        folder_ids=folder_id or [],
        unfoldered=unfoldered,
        tag_roots=tag_id or [],
        conjunct_roots=conjunct_tag_id or [],
        exclude_roots=exclude_tag_id or [],
        exclude_undo_roots=exclude_tag_undo_id or [],
        exclude_folder_ids=exclude_folder_id or [],
        tag_match_all=tag_match_all,
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
        .options(*LIST_LOAD_OPTIONS)
    )
    result = await db.execute(q)
    notes = result.scalars().unique().all()
    return await _notes_to_read_models(db, user.id, list(notes), for_list=True)


@router.get("", response_model=list[NoteRead])
async def list_notes(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    folder_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    unfoldered: Annotated[bool, Query()] = False,
    trash_only: Annotated[bool, Query()] = False,
    tag_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    conjunct_tag_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    exclude_tag_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    exclude_tag_undo_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    exclude_folder_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    tag_match_all: Annotated[bool, Query()] = False,
) -> list[NoteRead]:
    if trash_only:
        result = await db.execute(
            select(Note)
            .options(*LIST_LOAD_OPTIONS)
            .where(Note.owner_id == user.id, Note.deleted_at.is_not(None))
            .order_by(Note.deleted_at.desc())
        )
        trash_notes = result.scalars().unique().all()
        return await _notes_to_read_models(db, user.id, list(trash_notes), for_list=True)

    filters = _filters_from_query(
        folder_id,
        unfoldered,
        tag_id,
        conjunct_tag_id,
        exclude_tag_id,
        exclude_tag_undo_id,
        exclude_folder_id,
        tag_match_all,
    )
    q = await build_note_list_query(db, user.id, filters)
    result = await db.execute(q)
    notes = result.scalars().unique().all()
    return await _notes_to_read_models(db, user.id, list(notes), for_list=True)


@router.get("/search", response_model=list[NoteRead])
async def search_notes(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    q: Annotated[str, Query(min_length=1, max_length=200)],
    folder_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    unfoldered: Annotated[bool, Query()] = False,
    tag_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    conjunct_tag_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    exclude_tag_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    exclude_tag_undo_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    exclude_folder_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    tag_match_all: Annotated[bool, Query()] = False,
) -> list[NoteRead]:
    filters = _filters_from_query(
        folder_id,
        unfoldered,
        tag_id,
        conjunct_tag_id,
        exclude_tag_id,
        exclude_tag_undo_id,
        exclude_folder_id,
        tag_match_all,
    )
    base = await build_note_list_query(
        db, user.id, filters, text_predicate=note_search_predicate(q)
    )
    result = await db.execute(base)
    notes = result.scalars().unique().all()
    return await _notes_to_read_models(db, user.id, list(notes), for_list=True)


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
    return _note_read_with_access(loaded, Access.owner)


@router.get("/{note_id}", response_model=NoteRead)
async def get_note(
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NoteRead:
    note, access = await get_note_access(db, note_id, user.id)
    return await note_read_for_requester(db, user.id, note, access)


@router.post("/{note_id}/take-ownership", response_model=NoteRead)
async def take_ownership(
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin)],
) -> NoteRead:
    """Админ становится создателем заметки, которой с ним поделились."""
    note, access = await get_note_access(db, note_id, user.id)
    if access == Access.owner:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Вы уже создатель этой заметки",
        )
    note = await take_note_ownership(db, note, user)
    return await note_read_for_requester(db, user.id, note, Access.owner)


@router.patch("/{note_id}", response_model=NoteRead)
async def update_note(
    note_id: uuid.UUID,
    body: NoteUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NoteRead:
    updates = body.model_dump(exclude_unset=True)
    note, access = await get_note_access(db, note_id, user.id)

    async def finalize() -> NoteRead:
        return await note_read_for_requester(db, user.id, note, access)

    if not updates:
        return await finalize()

    folder_only = updates.keys() <= {"folder_id"}

    if folder_only:
        if note.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change folder for trashed note",
            )
        fid_raw = updates.get("folder_id")
        fid: uuid.UUID | None = fid_raw if fid_raw is not None else None
        await _validate_folder_for_owner(db, fid, user.id)
        if note.owner_id == user.id:
            if note.folder_id != fid:
                note.folder_id = fid
                note.updated_at = datetime.now(timezone.utc)
                await db.flush()
        else:
            await upsert_placement(db, user.id, note_id, fid)
            await db.flush()
        return await finalize()

    ensure_note_editable(note, access)

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
        if note.owner_id == user.id:
            if note.folder_id != fid:
                await _validate_folder_for_owner(db, fid, user.id)
                note.folder_id = fid
                changed = True
        else:
            await _validate_folder_for_owner(db, fid, user.id)
            await upsert_placement(db, user.id, note_id, fid)
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
    return await finalize()


@router.delete("/trash", status_code=status.HTTP_204_NO_CONTENT)
async def empty_trash(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    result = await db.execute(
        select(Note).where(Note.owner_id == user.id, Note.deleted_at.is_not(None))
    )
    for note in result.scalars().all():
        await db.delete(note)


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
    # server_onupdate на updated_at сбрасывает колонку после UPDATE;
    # без повторной загрузки from_note ловит MissingGreenlet (500).
    loaded = await _note_with_tags(db, note.id)
    return _note_read_with_access(loaded, Access.owner)


@router.delete("/{note_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def purge_note(
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    note = await require_trashed_note_owner(db, note_id, user.id)
    await db.delete(note)


@router.post("/{note_id}/tags/by-name", response_model=TagAttachByNameResult)
async def attach_tag_by_name(
    note_id: uuid.UUID,
    body: TagAttachByName,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> TagAttachByNameResult:
    """Метки владельца на своих заметках; у получателя шаринга — только его личные метки."""
    note, access = await get_note_access(db, note_id, user.id)
    if note.owner_id == user.id:
        ensure_note_editable(note, access)
        tag = await get_or_create_root_tag(db, user.id, body.name)
        if tag not in note.tags:
            note.tags.append(tag)
            note.updated_at = datetime.now(timezone.utc)
        await db.flush()
    else:
        tag = await get_or_create_root_tag(db, user.id, body.name)
        if not await has_personal_tag(db, user.id, note_id, tag.id):
            await add_personal_tag_link(db, user.id, note_id, tag.id)
            await db.flush()
    return TagAttachByNameResult(
        note=await note_read_for_requester(db, user.id, note, access),
        tag=TagRead.model_validate(tag),
    )


@router.post("/{note_id}/tags/{tag_id}", response_model=NoteRead)
async def attach_tag(
    note_id: uuid.UUID,
    tag_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NoteRead:
    note, access = await get_note_access(db, note_id, user.id)
    tag_result = await db.execute(select(Tag).where(Tag.id == tag_id))
    tag = tag_result.scalar_one_or_none()
    if tag is None or tag.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")

    if note.owner_id == user.id:
        ensure_note_editable(note, access)
        if tag not in note.tags:
            note.tags.append(tag)
            note.updated_at = datetime.now(timezone.utc)
        await db.flush()
    else:
        if not await has_personal_tag(db, user.id, note_id, tag_id):
            await add_personal_tag_link(db, user.id, note_id, tag_id)
            await db.flush()

    return await note_read_for_requester(db, user.id, note, access)


@router.delete("/{note_id}/tags/{tag_id}", response_model=NoteRead)
async def detach_tag(
    note_id: uuid.UUID,
    tag_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> NoteRead:
    note, access = await get_note_access(db, note_id, user.id)
    if note.owner_id == user.id:
        ensure_note_editable(note, access)
        before = len(note.tags)
        note.tags = [t for t in note.tags if t.id != tag_id]
        if len(note.tags) < before:
            note.updated_at = datetime.now(timezone.utc)
            await db.flush()
    else:
        if await has_personal_tag(db, user.id, note_id, tag_id):
            await remove_personal_tag_link(db, user.id, note_id, tag_id)
            await db.flush()
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not on note")

    return await note_read_for_requester(db, user.id, note, access)
