import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NoteChecklistLink(Base):
    """Ссылка «чек-лист»: по токену можно только ставить и снимать галочки в заметке.

    Отдельная таблица, а не роль у NotePublicLink: у заметки может быть одновременно
    обычная ссылка и чек-лист со своим адресом, и отзываются они независимо.
    """

    __tablename__ = "note_checklist_links"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(96), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
