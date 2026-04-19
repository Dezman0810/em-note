import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.note import Note
    from app.models.user import User


class ShareRole(str, enum.Enum):
    viewer = "viewer"
    editor = "editor"


class NoteShare(Base):
    __tablename__ = "note_shares"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shared_with_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    invite_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=ShareRole.viewer.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    note: Mapped["Note"] = relationship("Note", back_populates="shares")
    shared_with_user: Mapped["User | None"] = relationship("User", foreign_keys=[shared_with_user_id])
