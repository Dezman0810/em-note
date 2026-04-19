from sqlalchemy import Column, ForeignKey, Table, Uuid

from app.models.base import Base

note_tag = Table(
    "note_tags",
    Base.metadata,
    Column(
        "note_id",
        Uuid(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Uuid(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
