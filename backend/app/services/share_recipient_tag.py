"""Личная метка у получателя шаринга для фильтра «Доступ по email»."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.share import NoteShare
from app.services.note_personal_view import add_personal_tag_link, has_personal_tag
from app.services.tag_ops import get_or_create_root_tag

# Единое имя корневой метки у каждого получателя (личные метки, не видны владельцу).
SHARED_ACCESS_EMAIL_TAG_NAME = "Доступ по email"


async def attach_share_access_email_personal_tag(
    db: AsyncSession, recipient_user_id: uuid.UUID, note_id: uuid.UUID
) -> None:
    """Вешает на заметку личную метку «Доступ по email» у получателя (идемпотентно)."""
    tag = await get_or_create_root_tag(db, recipient_user_id, SHARED_ACCESS_EMAIL_TAG_NAME)
    if await has_personal_tag(db, recipient_user_id, note_id, tag.id):
        return
    await add_personal_tag_link(db, recipient_user_id, note_id, tag.id)


async def ensure_share_access_tags_for_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Гарантирует метку «Доступ по email» на всех заметках, расшаренных пользователю (идемпотентно)."""
    res = await db.execute(
        select(NoteShare.note_id).where(NoteShare.shared_with_user_id == user_id)
    )
    for row in res.fetchall():
        await attach_share_access_email_personal_tag(db, user_id, row[0])
