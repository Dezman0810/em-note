import uuid
from typing import TYPE_CHECKING

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.utc_types import UtcDatetime

if TYPE_CHECKING:
    from app.models.share import NoteShare as NoteShareOrm


class NoteShareCreate(BaseModel):
    shared_with_user_id: uuid.UUID | None = None
    invite_email: EmailStr | None = None
    role: str = Field(default="viewer", pattern="^(viewer|editor)$")

    @model_validator(mode="after")
    def validate_targets(self) -> "NoteShareCreate":
        if not self.shared_with_user_id and not self.invite_email:
            raise ValueError("Either shared_with_user_id or invite_email is required")
        if self.shared_with_user_id and self.invite_email:
            raise ValueError("Provide only one of shared_with_user_id or invite_email")
        return self


class NoteShareUpdate(BaseModel):
    role: str = Field(pattern="^(viewer|editor)$")


class NoteShareRead(BaseModel):
    id: uuid.UUID
    note_id: uuid.UUID
    shared_with_user_id: uuid.UUID | None
    invite_email: str | None
    sharee_email: str | None = Field(
        default=None,
        description="Отображаемый email адресата (invite или профиль при привязке к пользователю).",
    )
    role: str
    created_at: UtcDatetime

    model_config = {"from_attributes": True}


def note_share_to_read(note: "NoteShareOrm") -> NoteShareRead:
    """Собираем итоговый email адресата: сохранённое приглашение или email профиля при shared_with_user_id."""
    sharee_email = note.invite_email
    if not sharee_email and note.shared_with_user is not None:
        sharee_email = note.shared_with_user.email
    return NoteShareRead(
        id=note.id,
        note_id=note.note_id,
        shared_with_user_id=note.shared_with_user_id,
        invite_email=note.invite_email,
        sharee_email=sharee_email,
        role=note.role,
        created_at=note.created_at,
    )
