from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.smtp import UserSmtpSettings
from app.models.user import User

router = APIRouter(prefix="/users/me", tags=["users"])


class SmtpSettingsPayload(BaseModel):
    host: str = Field(..., max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    username: str = Field(..., max_length=320)
    password: str = Field(..., min_length=1, max_length=256)
    from_address: EmailStr
    use_tls: bool = True


class SmtpSettingsRead(BaseModel):
    host: str
    port: int
    username: str
    from_address: str
    use_tls: bool

    model_config = {"from_attributes": True}


@router.put("/smtp", response_model=SmtpSettingsRead)
async def upsert_smtp_settings(
    body: SmtpSettingsPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> UserSmtpSettings:
    result = await db.execute(select(UserSmtpSettings).where(UserSmtpSettings.user_id == user.id))
    row = result.scalar_one_or_none()
    if row is None:
        row = UserSmtpSettings(user_id=user.id)
        db.add(row)
    row.host = body.host
    row.port = body.port
    row.username = body.username
    row.password_encrypted = body.password.encode("utf-8")
    row.from_address = str(body.from_address)
    row.use_tls = body.use_tls
    await db.flush()
    await db.refresh(row)
    return row


@router.get("/smtp", response_model=SmtpSettingsRead | None)
async def get_smtp_settings(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> UserSmtpSettings | None:
    result = await db.execute(select(UserSmtpSettings).where(UserSmtpSettings.user_id == user.id))
    return result.scalar_one_or_none()


@router.delete("/smtp", status_code=status.HTTP_204_NO_CONTENT)
async def delete_smtp_settings(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    result = await db.execute(select(UserSmtpSettings).where(UserSmtpSettings.user_id == user.id))
    row = result.scalar_one_or_none()
    if row is not None:
        await db.delete(row)
