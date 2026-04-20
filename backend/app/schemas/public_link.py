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
