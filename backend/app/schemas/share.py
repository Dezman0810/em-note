import uuid

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.utc_types import UtcDatetime


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


class NoteShareRead(BaseModel):
    id: uuid.UUID
    note_id: uuid.UUID
    shared_with_user_id: uuid.UUID | None
    invite_email: str | None
    role: str
    created_at: UtcDatetime

    model_config = {"from_attributes": True}
