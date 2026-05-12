"""Отправка EmailMessage через aiosmtplib (общая логика для пользовательского SMTP и relay из настроек сервера)."""

from email.message import EmailMessage

import aiosmtplib
from fastapi import HTTPException, status


async def deliver_email_message(
    msg: EmailMessage,
    *,
    hostname: str,
    port: int,
    username: str,
    password: str | bytes | None,
    use_tls: bool,
    start_tls: bool | None,
) -> None:
    pwd: str | None
    if password is None:
        pwd = None
    elif isinstance(password, bytes):
        pwd = password.decode("utf-8")
    else:
        pwd = password

    try:
        await aiosmtplib.send(
            msg,
            hostname=hostname,
            port=port,
            username=username,
            password=pwd,
            use_tls=use_tls,
            start_tls=start_tls,
        )
    except aiosmtplib.SMTPException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SMTP error: {exc}",
        ) from exc
