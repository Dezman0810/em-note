import uuid

from pydantic import BaseModel, EmailStr, Field, computed_field

from app.config import settings
from app.schemas.utc_types import UtcDatetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=120)


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    created_at: UtcDatetime
    can_create_notes: bool = True

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def is_admin(self) -> bool:
        a = (settings.admin_email or "").strip().lower()
        return bool(a) and self.email.strip().lower() == a


class UserAdminListItem(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    created_at: UtcDatetime
    can_create_notes: bool

    model_config = {"from_attributes": True}


class UserAdminUpdate(BaseModel):
    can_create_notes: bool


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
