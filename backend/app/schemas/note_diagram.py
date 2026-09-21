import uuid

from pydantic import BaseModel, Field

from app.schemas.utc_types import UtcDatetime


class NoteDiagramListItem(BaseModel):
    note_id: uuid.UUID
    note_title: str
    schema_index: int
    block_id: str | None = None
    caption: str
    element_count: int = 0
    can_edit: bool
    my_access: str
    updated_at: UtcDatetime
    tag_names: list[str] = Field(default_factory=list)


class NoteDiagramDetail(NoteDiagramListItem):
    scene: str


class NoteDiagramPatch(BaseModel):
    scene: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, max_length=80)
    block_id: str | None = None
