import uuid

from pydantic import BaseModel, EmailStr, Field


class SendNoteMailRequest(BaseModel):
    note_id: uuid.UUID
    to_emails: list[EmailStr] = Field(..., min_length=1, max_length=20)
    extra_message: str | None = Field(default=None, max_length=5000)
