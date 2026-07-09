from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field

from app.schemas.utc_types import UtcDatetime


class UserContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr


class UserContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None


class UserContactRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    email: str
    created_at: UtcDatetime
    updated_at: UtcDatetime

    model_config = {"from_attributes": True}
