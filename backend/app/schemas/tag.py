import uuid

from pydantic import BaseModel, Field

from app.schemas.utc_types import UtcDatetime


class TagCreate(BaseModel):
    name: str = Field(..., max_length=120)
    parent_id: uuid.UUID | None = None


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    parent_id: uuid.UUID | None = None


class TagRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    slug: str
    depth: int
    created_at: UtcDatetime

    model_config = {"from_attributes": True}


class TagNoteCountRead(BaseModel):
    tag_id: uuid.UUID
    count: int


class TagAttachByName(BaseModel):
    """Создать корневую метку у владельца заметки (если нет) и прикрепить к заметке."""

    name: str = Field(..., max_length=120)
