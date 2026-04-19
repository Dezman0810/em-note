import uuid

from pydantic import BaseModel, Field

from app.schemas.utc_types import UtcDatetime


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)


class FolderRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    created_at: UtcDatetime

    model_config = {"from_attributes": True}
