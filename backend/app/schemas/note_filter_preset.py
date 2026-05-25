from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.utc_types import UtcDatetime

_MAX_IDS_EACH = 120


def _dedupe_ids(ids: list[uuid.UUID]) -> list[uuid.UUID]:
    seen: set[uuid.UUID] = set()
    out: list[uuid.UUID] = []
    for u in ids:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


class _PresetFilterFieldsMixin(BaseModel):
    search_query: str | None = Field(default=None, max_length=200)
    folder_ids: list[uuid.UUID] = Field(default_factory=list)
    exclude_folder_ids: list[uuid.UUID] = Field(default_factory=list)
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    exclude_tag_ids: list[uuid.UUID] = Field(default_factory=list)
    exclude_tag_undo_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator(
        "folder_ids",
        "exclude_folder_ids",
        "tag_ids",
        "exclude_tag_ids",
        "exclude_tag_undo_ids",
        mode="after",
    )
    @classmethod
    def _validate_id_lists(cls, ids: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(ids) > _MAX_IDS_EACH:
            raise ValueError(f"Не больше {_MAX_IDS_EACH} элементов в списке")
        return _dedupe_ids(ids)


class FilterPresetCreate(_PresetFilterFieldsMixin):
    name: str = Field(..., min_length=1, max_length=160)


class FilterPresetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    search_query: str | None = Field(default=None, max_length=200)
    folder_ids: list[uuid.UUID] | None = None
    exclude_folder_ids: list[uuid.UUID] | None = None
    tag_ids: list[uuid.UUID] | None = None
    exclude_tag_ids: list[uuid.UUID] | None = None
    exclude_tag_undo_ids: list[uuid.UUID] | None = None

    model_config = {"extra": "forbid"}

    @field_validator(
        "folder_ids",
        "exclude_folder_ids",
        "tag_ids",
        "exclude_tag_ids",
        "exclude_tag_undo_ids",
        mode="after",
    )
    @classmethod
    def _validate_optional_lists(cls, v: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if v is None:
            return None
        if len(v) > _MAX_IDS_EACH:
            raise ValueError(f"Не больше {_MAX_IDS_EACH} элементов в списке")
        return _dedupe_ids(v)


class FilterPresetRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    search_query: str | None = None
    folder_ids: list[uuid.UUID] = Field(default_factory=list)
    exclude_folder_ids: list[uuid.UUID] = Field(default_factory=list)
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    exclude_tag_ids: list[uuid.UUID] = Field(default_factory=list)
    exclude_tag_undo_ids: list[uuid.UUID] = Field(default_factory=list)
    sort_order: int
    created_at: UtcDatetime
    updated_at: UtcDatetime

    model_config = {"from_attributes": True}

    @field_validator(
        "folder_ids",
        "exclude_folder_ids",
        "tag_ids",
        "exclude_tag_ids",
        "exclude_tag_undo_ids",
        mode="before",
    )
    @classmethod
    def _coerce_uuid_lists(cls, v: Any) -> Any:
        if v is None:
            return []
        if isinstance(v, list):
            return [uuid.UUID(str(x)) for x in v]
        return v
