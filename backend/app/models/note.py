import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.note_tag import note_tag

if TYPE_CHECKING:
    from app.models.folder import Folder
    from app.models.share import NoteShare
    from app.models.tag import Tag
    from app.models.user import User


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    content_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    content_plain: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        server_onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    accent_color: Mapped[str] = mapped_column(String(16), nullable=False, default="")

    owner: Mapped["User"] = relationship("User", back_populates="notes", foreign_keys=[owner_id])
    folder: Mapped["Folder | None"] = relationship("Folder", back_populates="notes")
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary=note_tag, back_populates="notes"
    )
    shares: Mapped[list["NoteShare"]] = relationship(
        "NoteShare", back_populates="note", cascade="all, delete-orphan"
    )
