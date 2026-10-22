import uuid

from pydantic import BaseModel, Field

from app.schemas.note import NoteRead
from app.schemas.utc_types import UtcDatetime


class NotePublicLinkUpsert(BaseModel):
    role: str = Field(pattern="^(viewer|editor)$")


class NotePublicLinkRead(BaseModel):
    token: str
    role: str
    created_at: UtcDatetime

    model_config = {"from_attributes": True}


class PublicNotePayload(BaseModel):
    note: NoteRead
    can_edit: bool
    role: str


class NoteChecklistLinkRead(BaseModel):
    token: str
    created_at: UtcDatetime

    model_config = {"from_attributes": True}


class PublicChecklistPayload(BaseModel):
    note: NoteRead


class ChecklistToggle(BaseModel):
    """Единственная операция по ссылке «чек-лист»: поставить или снять галочку у пункта."""

    index: int = Field(ge=0, le=100_000)
    checked: bool
    # Текст пункта, который видит клиент: если владелец успел поменять список — 409.
    text: str = Field(max_length=20_000)
