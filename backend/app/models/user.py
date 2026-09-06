import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.folder import Folder
    from app.models.note import Note
    from app.models.smtp import UserSmtpSettings
    from app.models.tag import Tag
    from app.models.habit import Habit
    from app.models.habit_public_link import HabitPublicLink
    from app.models.user_contact import UserContact
    from app.models.user_note_filter_preset import UserNoteFilterPreset


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    can_create_notes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_use_habits: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    notes: Mapped[list["Note"]] = relationship(
        "Note", back_populates="owner", foreign_keys="Note.owner_id"
    )
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", back_populates="user", cascade="all, delete-orphan"
    )
    folders: Mapped[list["Folder"]] = relationship(
        "Folder", back_populates="user", cascade="all, delete-orphan"
    )
    smtp_settings: Mapped["UserSmtpSettings | None"] = relationship(
        "UserSmtpSettings", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    filter_presets: Mapped[list["UserNoteFilterPreset"]] = relationship(
        "UserNoteFilterPreset", back_populates="user", cascade="all, delete-orphan"
    )
    contacts: Mapped[list["UserContact"]] = relationship(
        "UserContact", back_populates="user", cascade="all, delete-orphan"
    )
    habits: Mapped[list["Habit"]] = relationship(
        "Habit", back_populates="user", cascade="all, delete-orphan"
    )
    habit_public_link: Mapped["HabitPublicLink | None"] = relationship(
        "HabitPublicLink", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
