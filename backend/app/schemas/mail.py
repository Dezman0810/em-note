import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SendNoteMailRequest(BaseModel):
    note_id: uuid.UUID
    to_emails: list[EmailStr] = Field(..., min_length=1, max_length=20)
    extra_message: str | None = Field(default=None, max_length=5000)


class NoteMailSendRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    to_emails: list[str]
    sent_at: datetime
    sender_email: str
