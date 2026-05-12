import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.folder import Folder
    from app.models.note import Note
    from app.models.user import User


class NoteUserPlacement(Base):
    """Куда получатель шаринга кладёт заметку в своих папках (не трогает folder_id владельца)."""

    __tablename__ = "note_user_placements"
    __table_args__ = (UniqueConstraint("user_id", "note_id", name="uq_note_user_placement"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    note: Mapped["Note"] = relationship("Note", foreign_keys=[note_id])
    folder: Mapped["Folder | None"] = relationship("Folder", foreign_keys=[folder_id])
