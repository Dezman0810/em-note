"""Привязка записей note_shares от invite_email к зарегистрированному пользователю."""

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.share import NoteShare
from app.models.user import User
from app.services.share_recipient_tag import attach_share_access_email_personal_tag


async def claim_invite_shares_for_user(db: AsyncSession, user: User) -> None:
    if not (user.email or "").strip():
        return
    email_norm = user.email.strip().lower()
    res = await db.execute(
        update(NoteShare)
        .where(
            NoteShare.invite_email.isnot(None),
            func.lower(NoteShare.invite_email) == email_norm,
            NoteShare.shared_with_user_id.is_(None),
        )
        .values(shared_with_user_id=user.id)
        .returning(NoteShare.note_id)
    )
    for row in res.fetchall():
        await attach_share_access_email_personal_tag(db, user.id, row[0])
