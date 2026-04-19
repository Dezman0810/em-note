from email.message import EmailMessage
from typing import Annotated

import aiosmtplib
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.smtp import UserSmtpSettings
from app.models.user import User
from app.schemas.mail import SendNoteMailRequest
from app.services.note_access import get_note_access
from app.utils.text import plain_text_from_tiptap_json

router = APIRouter(prefix="/mail", tags=["mail"])


@router.post("/send-note")
async def send_note_by_mail(
    body: SendNoteMailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    note, _ = await get_note_access(db, body.note_id, user.id)

    smtp_result = await db.execute(
        select(UserSmtpSettings).where(UserSmtpSettings.user_id == user.id)
    )
    smtp = smtp_result.scalar_one_or_none()
    if smtp is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configure SMTP in account settings first",
        )

    plain_body = note.content_plain or plain_text_from_tiptap_json(note.content_json)
    text_parts = [
        f"Note: {note.title}",
        "",
        plain_body[:8000],
    ]
    if body.extra_message:
        text_parts.extend(["", "---", body.extra_message])
    text = "\n".join(text_parts)

    msg = EmailMessage()
    msg["From"] = smtp.from_address
    msg["To"] = ", ".join(str(e) for e in body.to_emails)
    msg["Subject"] = f"Shared note: {note.title}"[:200]
    msg.set_content(text)

    password: str | bytes | None = smtp.password_encrypted
    if isinstance(password, bytes):
        password = password.decode("utf-8")

    try:
        await aiosmtplib.send(
            msg,
            hostname=smtp.host,
            port=smtp.port,
            username=smtp.username,
            password=password,
            start_tls=smtp.use_tls,
        )
    except aiosmtplib.SMTPException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SMTP error: {exc}",
        ) from exc

    return {"status": "sent"}
