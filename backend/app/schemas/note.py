import re
import uuid
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

from app.schemas.utc_types import UtcDatetime

if TYPE_CHECKING:
    from app.models.note import Note

_ACCENT_RE = re.compile(r"^$|^#[0-9A-Fa-f]{6}$")


def _normalize_accent(v: str | None) -> str:
    s = (v or "").strip()
    if not s:
        return ""
    if not _ACCENT_RE.match(s):
        raise ValueError("accent_color must be empty or #RRGGBB")
    return s.lower()


class NoteCreate(BaseModel):
    title: str = Field(default="", max_length=500)
    content_json: str = Field(default="{}")
    content_plain: str | None = None
    folder_id: uuid.UUID | None = None
    accent_color: str = Field(default="", max_length=16)

    @field_validator("accent_color")
    @classmethod
    def validate_accent_create(cls, v: str) -> str:
        return _normalize_accent(v)


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    content_json: str | None = None
    content_plain: str | None = None
    folder_id: uuid.UUID | None = None
    accent_color: str | None = None

    @field_validator("accent_color")
    @classmethod
    def validate_accent_update(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _normalize_accent(v)


class NoteRead(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    content_json: str
    content_plain: str
    created_at: UtcDatetime
    updated_at: UtcDatetime
    deleted_at: UtcDatetime | None
    folder_id: uuid.UUID | None = None
    accent_color: str = ""
    tag_ids: list[uuid.UUID] = []

    model_config = {"from_attributes": True}

    @classmethod
    def from_note(cls, note: "Note") -> "NoteRead":
        return cls(
            id=note.id,
            owner_id=note.owner_id,
            title=note.title,
            content_json=note.content_json,
            content_plain=note.content_plain,
            created_at=note.created_at,
            updated_at=note.updated_at,
            deleted_at=note.deleted_at,
            folder_id=note.folder_id,
            accent_color=note.accent_color or "",
            tag_ids=[t.id for t in note.tags],
        )
