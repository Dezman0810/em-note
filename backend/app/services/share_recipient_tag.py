"""Личная метка у получателя шаринга для фильтра «Доступ по email»."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note_user_personal_tag import note_user_personal_tag
from app.models.share import NoteShare
from app.models.tag import Tag
from app.services.tag_ops import get_or_create_root_tag

# Единое имя корневой метки у каждого получателя (личные метки, не видны владельцу).
SHARED_ACCESS_EMAIL_TAG_NAME = "Доступ по email"


def _missing_share_access_note_ids_stmt(user_id: uuid.UUID):
    """note_id всех шеров пользователя, где ещё нет его корневой метки «Доступ по email»."""
    already_tagged = (
        select(note_user_personal_tag.c.note_id)
        .join(Tag, Tag.id == note_user_personal_tag.c.tag_id)
        .where(
            note_user_personal_tag.c.user_id == user_id,
            note_user_personal_tag.c.note_id == NoteShare.note_id,
            Tag.user_id == user_id,
            Tag.parent_id.is_(None),
            func.lower(Tag.name) == SHARED_ACCESS_EMAIL_TAG_NAME.lower(),
        )
    )
    return (
        select(NoteShare.note_id)
        .where(NoteShare.shared_with_user_id == user_id)
        .where(~already_tagged.exists())
        .distinct()
    )


async def _insert_personal_tag_links(
    db: AsyncSession, user_id: uuid.UUID, note_ids: Sequence[uuid.UUID], tag_id: uuid.UUID
) -> None:
    """Одним INSERT ... ON CONFLICT DO NOTHING (PK на user_id/note_id/tag_id)."""
    if not note_ids:
        return
    await db.execute(
        pg_insert(note_user_personal_tag)
        .values([{"user_id": user_id, "note_id": nid, "tag_id": tag_id} for nid in note_ids])
        .on_conflict_do_nothing()
    )


async def attach_share_access_email_personal_tags(
    db: AsyncSession, recipient_user_id: uuid.UUID, note_ids: Sequence[uuid.UUID]
) -> None:
    """Вешает личную метку «Доступ по email» на перечисленные заметки (идемпотентно)."""
    if not note_ids:
        return
    tag = await get_or_create_root_tag(db, recipient_user_id, SHARED_ACCESS_EMAIL_TAG_NAME)
    await _insert_personal_tag_links(db, recipient_user_id, note_ids, tag.id)


async def attach_share_access_email_personal_tag(
    db: AsyncSession, recipient_user_id: uuid.UUID, note_id: uuid.UUID
) -> None:
    """Вешает на заметку личную метку «Доступ по email» у получателя (идемпотентно)."""
    await attach_share_access_email_personal_tags(db, recipient_user_id, [note_id])


async def ensure_share_access_tags_for_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Гарантирует метку «Доступ по email» на всех заметках, расшаренных пользователю.

    Один SELECT в типичном случае (доставлять нечего); иначе плюс поиск/создание
    корневой метки и один batch-INSERT.
    """
    missing = (
        (await db.execute(_missing_share_access_note_ids_stmt(user_id))).scalars().all()
    )
    await attach_share_access_email_personal_tags(db, user_id, list(missing))
