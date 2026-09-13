"""Админ забирает чужую расшаренную заметку себе как создатель."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.note import Note
from app.models.share import NoteShare, ShareRole
from app.models.tag import Tag
from app.models.user import User
from app.services.folder_access import assert_folders_owned
from app.services.note_personal_view import (
    add_personal_tag_link,
    personal_tag_ids_map,
    placement_folder_map,
    remove_personal_tag_link,
    upsert_placement,
)
from app.services.share_recipient_tag import (
    SHARED_ACCESS_EMAIL_TAG_NAME,
    attach_share_access_email_personal_tag,
)


async def take_note_ownership(db: AsyncSession, note: Note, admin: User) -> Note:
    """Админ становится владельцем. Прежний автор остаётся с правом редактирования."""
    old_owner_id = note.owner_id
    if old_owner_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Вы уже создатель этой заметки",
        )
    if note.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя забрать заметку из корзины",
        )

    admin_share = (
        await db.execute(
            select(NoteShare).where(
                NoteShare.note_id == note.id,
                NoteShare.shared_with_user_id == admin.id,
            )
        )
    ).scalar_one_or_none()
    if admin_share is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Забрать можно только заметку, которой с вами поделились",
        )

    old_folder_id = note.folder_id
    old_tags = list(note.tags)
    placements = await placement_folder_map(db, admin.id, [note.id])
    admin_folder_id = placements.get(note.id)
    admin_tag_ids = (await personal_tag_ids_map(db, admin.id, [note.id])).get(note.id, [])

    if admin_folder_id is not None:
        await assert_folders_owned(db, [admin_folder_id], admin.id)

    note.tags = []
    note.owner_id = admin.id
    note.folder_id = admin_folder_id

    await upsert_placement(db, admin.id, note.id, None)
    if old_folder_id is not None:
        await upsert_placement(db, old_owner_id, note.id, old_folder_id)

    for tag in old_tags:
        await add_personal_tag_link(db, old_owner_id, note.id, tag.id)

    skip_names = {SHARED_ACCESS_EMAIL_TAG_NAME.casefold()}
    for tag_id in admin_tag_ids:
        await remove_personal_tag_link(db, admin.id, note.id, tag_id)
        tag = await db.get(Tag, tag_id)
        if tag is None or tag.user_id != admin.id:
            continue
        if tag.name.casefold() in skip_names:
            continue
        note.tags.append(tag)

    await db.delete(admin_share)

    already_old = (
        await db.execute(
            select(NoteShare.id).where(
                NoteShare.note_id == note.id,
                NoteShare.shared_with_user_id == old_owner_id,
            )
        )
    ).scalar_one_or_none()
    if already_old is None:
        db.add(
            NoteShare(
                note_id=note.id,
                shared_with_user_id=old_owner_id,
                role=ShareRole.editor.value,
            )
        )
    await attach_share_access_email_personal_tag(db, old_owner_id, note.id)
    await db.flush()

    loaded = (
        await db.execute(select(Note).options(selectinload(Note.tags)).where(Note.id == note.id))
    ).scalar_one()
    return loaded
