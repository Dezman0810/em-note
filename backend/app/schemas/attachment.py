import uuid

from pydantic import BaseModel


class AttachmentRead(BaseModel):
    id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    is_image: bool

    model_config = {"from_attributes": True}

    @classmethod
    def from_row(cls, row: object) -> "AttachmentRead":
        ct = getattr(row, "content_type", "") or ""
        return cls(
            id=getattr(row, "id"),
            original_filename=getattr(row, "original_filename", "") or "",
            content_type=ct or "application/octet-stream",
            size_bytes=int(getattr(row, "size_bytes", 0)),
            is_image=ct.lower().startswith("image/"),
        )
