import logging
import uuid
from email.message import EmailMessage
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.models.note_mail_send import NoteMailSend
from app.models.smtp import UserSmtpSettings
from app.models.user import User
from app.schemas.mail import NoteMailSendRead, SendNoteMailRequest
from app.services.note_access import get_note_access
from app.services.smtp_deliver import deliver_email_message
from app.utils.text import plain_text_from_tiptap_json

router = APIRouter(prefix="/mail", tags=["mail"])

logger = logging.getLogger(__name__)

MISSING_MAIL_HISTORY_TABLE_DETAIL = (
    "В базе нет таблицы истории отправок почты (note_mail_sends). "
    "На контейнере API выполните: alembic upgrade head "
    "(миграция 202605121000). Например: docker compose exec api alembic upgrade head"
)


def _is_missing_note_mail_sends(exc: BaseException) -> bool:
    parts: list[str] = [str(exc)]
    orig = getattr(exc, "orig", None)
    if orig is not None:
        parts.append(str(orig))
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        parts.append(str(cause))
    msg = " ".join(parts).lower()
    return "note_mail_sends" in msg and ("does not exist" in msg or "undefinedtable" in msg.replace("_", ""))


def _split_to_emails_csv(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


@router.post("/send-note")
async def send_note_by_mail(
    body: SendNoteMailRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    note, _ = await get_note_access(db, body.note_id, user.id)

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
    msg["To"] = ", ".join(str(e) for e in body.to_emails)
    msg["Subject"] = f"Shared note: {note.title}"[:200]
    msg.set_content(text)

    smtp_result = await db.execute(select(UserSmtpSettings).where(UserSmtpSettings.user_id == user.id))
    smtp = smtp_result.scalar_one_or_none()

    if smtp is not None:
        msg["From"] = smtp.from_address
        password = smtp.password_encrypted
        if isinstance(password, bytes):
            password = password.decode("utf-8")
        await deliver_email_message(
            msg,
            hostname=smtp.host,
            port=smtp.port,
            username=smtp.username,
            password=password,
            use_tls=False,
            start_tls=smtp.use_tls,
        )
    elif settings.smtp_relay_configured:
        msg["From"] = settings.smtp_relay_from_address.strip()
        use_immediate = settings.smtp_relay_tls_immediate
        use_starttls = settings.smtp_relay_start_tls and not use_immediate
        await deliver_email_message(
            msg,
            hostname=settings.smtp_relay_host.strip(),
            port=settings.smtp_relay_port,
            username=settings.smtp_relay_username.strip(),
            password=settings.smtp_relay_password_resolved(),
            use_tls=use_immediate,
            start_tls=use_starttls,
        )
    else:
        if settings.smtp_relay_needs_password:
            detail = (
                "Задайте пароль SMTP relay: переменная SMTP_RELAY_PASSWORD в backend/.env "
                "(или секретах сервера), либо SMTP_RELAY_PASSWORD_FILE — путь к файлу с паролем "
                "(например /run/secrets/… в Docker). Перезапустите API после изменения."
            )
        else:
            detail = (
                "Нет SMTP: задайте его в настройках аккаунта (PUT /api/users/me/smtp) "
                "или добавьте общий SMTP в окружение сервера: SMTP_RELAY_HOST, SMTP_RELAY_PORT, "
                "SMTP_RELAY_USERNAME, SMTP_RELAY_PASSWORD, SMTP_RELAY_FROM_ADDRESS "
                "(см. backend/.env.example)."
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    to_csv = ",".join(str(e).strip().lower() for e in body.to_emails)
    db.add(
        NoteMailSend(
            note_id=body.note_id,
            sender_user_id=user.id,
            to_addresses=to_csv,
        )
    )
    try:
        await db.flush()
    except DBAPIError as e:
        if _is_missing_note_mail_sends(e):
            logger.warning("note_mail_sends missing on flush: %s", e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=MISSING_MAIL_HISTORY_TABLE_DETAIL,
            ) from e
        raise
    logger.info(
        "mail_send_logged note_id=%s sender_user_id=%s recipients=%s",
        body.note_id,
        user.id,
        to_csv,
    )

    return {"status": "sent"}


@router.get("/notes/{note_id}/send-history", response_model=list[NoteMailSendRead])
async def list_note_mail_send_history(
    note_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[NoteMailSendRead]:
    await get_note_access(db, note_id, user.id)
    stmt = (
        select(NoteMailSend, User.email)
        .join(User, NoteMailSend.sender_user_id == User.id)
        .where(NoteMailSend.note_id == note_id)
        .order_by(NoteMailSend.sent_at.desc())
        .limit(50)
    )
    try:
        result = await db.execute(stmt)
    except DBAPIError as e:
        if _is_missing_note_mail_sends(e):
            logger.warning("note_mail_sends missing on send-history query: %s", e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=MISSING_MAIL_HISTORY_TABLE_DETAIL,
            ) from e
        raise
    out: list[NoteMailSendRead] = []
    for row in result.all():
        mail_send, sender_email = row[0], row[1]
        out.append(
            NoteMailSendRead(
                id=mail_send.id,
                to_emails=_split_to_emails_csv(mail_send.to_addresses),
                sent_at=mail_send.sent_at,
                sender_email=sender_email,
            )
        )
    return out