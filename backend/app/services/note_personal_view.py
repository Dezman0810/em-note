"""Персональные папка/метки получателя шаринга (не видны владельцу и другим)."""

import uuid
from collections import defaultdict

from sqlalchemy import exists, false, literal_column, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note
from app.models.note_tag import note_tag
from app.models.note_user_personal_tag import note_user_personal_tag
from app.models.note_user_placement import NoteUserPlacement
from app.models.share import NoteShare
from app.schemas.note import NoteRead
from app.services.note_access import Access


def folder_scope_predicate(
    user_id: uuid.UUID, folder_ids: list[uuid.UUID] | None, unfoldered: bool
):
    """Какая заметка попадает в выбранные папки / «Без папки» для данного пользователя."""
    owned = Note.owner_id == user_id
    shared_in = Note.id.in_(
        select(NoteShare.note_id).where(NoteShare.shared_with_user_id == user_id)
    )

    if unfoldered:
        owned_ok = owned & Note.folder_id.is_(None)
        has_nonroot = exists(
            select(literal_column("1")).select_from(NoteUserPlacement).where(
                NoteUserPlacement.user_id == user_id,
                NoteUserPlacement.note_id == Note.id,
                NoteUserPlacement.folder_id.isnot(None),
            )
        )
        shared_ok = shared_in & ~has_nonroot
        return owned_ok | shared_ok

    if not folder_ids:
        return true()

    owned_ok = owned & Note.folder_id.in_(folder_ids)
    in_personal = exists(
        select(literal_column("1")).select_from(NoteUserPlacement).where(
            NoteUserPlacement.user_id == user_id,
            NoteUserPlacement.note_id == Note.id,
            NoteUserPlacement.folder_id.in_(folder_ids),
        )
    )
    shared_ok = shared_in & in_personal
    return owned_ok | shared_ok


def folder_exclude_predicate(user_id: uuid.UUID, exclude_folder_ids: list[uuid.UUID]):
    """Заметка относится к одной из исключаемых папок (canonical или личное размещение шеренной)."""
    if not exclude_folder_ids:
        return false()

    owned = Note.owner_id == user_id
    shared_in = Note.id.in_(
        select(NoteShare.note_id).where(NoteShare.shared_with_user_id == user_id)
    )

    owned_in_excluded = owned & Note.folder_id.in_(exclude_folder_ids)
    placement_in_excluded = exists(
        select(literal_column("1")).select_from(NoteUserPlacement).where(
            NoteUserPlacement.user_id == user_id,
            NoteUserPlacement.note_id == Note.id,
            NoteUserPlacement.folder_id.in_(exclude_folder_ids),
        )
    )
    shared_in_excluded = shared_in & placement_in_excluded
    return owned_in_excluded | shared_in_excluded


def tag_match_predicate(user_id: uuid.UUID, tree_ids: list[uuid.UUID]):
    """Метки владельца на своих заметках + личные метки получателя на шеренных."""
    if not tree_ids:
        return false()

    owned = Note.owner_id == user_id
    shared_in = Note.id.in_(
        select(NoteShare.note_id).where(NoteShare.shared_with_user_id == user_id)
    )

    canonical_subq = select(note_tag.c.note_id).where(
        note_tag.c.tag_id.in_(tree_ids)
    )
    personal_subq = select(note_user_personal_tag.c.note_id).where(
        note_user_personal_tag.c.user_id == user_id,
        note_user_personal_tag.c.tag_id.in_(tree_ids),
    )
    owned_ok = owned & Note.id.in_(canonical_subq)
    shared_ok = shared_in & Note.id.in_(personal_subq)
    return owned_ok | shared_ok


async def placement_folder_map(
    db: AsyncSession, user_id: uuid.UUID, note_ids: list[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID | None]:
    if not note_ids:
        return {}
    rows = (
        await db.execute(
            select(NoteUserPlacement.note_id, NoteUserPlacement.folder_id).where(
                NoteUserPlacement.user_id == user_id,
                NoteUserPlacement.note_id.in_(note_ids),
            )
        )
    ).all()
    return {nid: fid for nid, fid in rows}


async def personal_tag_ids_map(
    db: AsyncSession, user_id: uuid.UUID, note_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    if not note_ids:
        return {}
    rows = (
        await db.execute(
            select(note_user_personal_tag.c.note_id, note_user_personal_tag.c.tag_id).where(
                note_user_personal_tag.c.user_id == user_id,
                note_user_personal_tag.c.note_id.in_(note_ids),
            )
        )
    ).all()
    out: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for nid, tid in rows:
        out[nid].append(tid)
    return dict(out)


async def upsert_placement(
    db: AsyncSession, user_id: uuid.UUID, note_id: uuid.UUID, folder_id: uuid.UUID | None
) -> None:
    row = (
        (
            await db.execute(
                select(NoteUserPlacement).where(
                    NoteUserPlacement.user_id == user_id,
                    NoteUserPlacement.note_id == note_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if folder_id is None:
        if row is not None:
            await db.delete(row)
        return
    if row is None:
        db.add(
            NoteUserPlacement(
                user_id=user_id,
                note_id=note_id,
                folder_id=folder_id,
            )
        )
    else:
        row.folder_id = folder_id


async def add_personal_tag_link(
    db: AsyncSession, user_id: uuid.UUID, note_id: uuid.UUID, tag_id: uuid.UUID
) -> None:
    await db.execute(
        note_user_personal_tag.insert().values(user_id=user_id, note_id=note_id, tag_id=tag_id)
    )


async def remove_personal_tag_link(
    db: AsyncSession, user_id: uuid.UUID, note_id: uuid.UUID, tag_id: uuid.UUID
) -> None:
    await db.execute(
        note_user_personal_tag.delete().where(
            note_user_personal_tag.c.user_id == user_id,
            note_user_personal_tag.c.note_id == note_id,
            note_user_personal_tag.c.tag_id == tag_id,
        )
    )


async def has_personal_tag(
    db: AsyncSession, user_id: uuid.UUID, note_id: uuid.UUID, tag_id: uuid.UUID
) -> bool:
    q = (
        await db.execute(
            select(note_user_personal_tag.c.note_id).where(
                note_user_personal_tag.c.user_id == user_id,
                note_user_personal_tag.c.note_id == note_id,
                note_user_personal_tag.c.tag_id == tag_id,
            )
        )
    ).scalar_one_or_none()
    return q is not None


def note_read_overlay(
    note: Note,
    access: Access,
    *,
    viewer_id: uuid.UUID,
    folder_effective: uuid.UUID | None,
    tag_ids_effective: list[uuid.UUID],
) -> NoteRead:
    if note.owner_id == viewer_id:
        base = NoteRead.from_note(note)
        return base.model_copy(update={"my_access": access.value})

    # Не трогаем relationship `note.tags`: в async это может вызвать implicit lazy-load и 500.
    _ma: str | None = None
    if access == Access.read:
        _ma = "read"
    elif access == Access.edit:
        _ma = "edit"
    elif access == Access.owner:
        _ma = "owner"
    return NoteRead(
        id=note.id,
        owner_id=note.owner_id,
        title=note.title,
        content_json=note.content_json,
        content_plain=note.content_plain,
        created_at=note.created_at,
        updated_at=note.updated_at,
        deleted_at=note.deleted_at,
        folder_id=folder_effective,
        accent_color=note.accent_color or "",
        reminder_at=note.reminder_at,
        tag_ids=tag_ids_effective,
        my_access=_ma,
    )
