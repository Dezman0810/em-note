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
    can_use_habits: bool = False
    can_use_grammar: bool = False
    can_use_budget: bool = False
    can_use_schemas: bool = False
    must_change_password: bool = False

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
    can_use_habits: bool
    can_use_grammar: bool = False
    can_use_budget: bool = False
    can_use_schemas: bool = False

    model_config = {"from_attributes": True}


class UserAdminUpdate(BaseModel):
    can_create_notes: bool | None = None
    can_use_habits: bool | None = None
    can_use_grammar: bool | None = None
    can_use_budget: bool | None = None
    can_use_schemas: bool | None = None


class UserAdminPasswordReset(BaseModel):
    email: str
    temporary_password: str


class UserChangePassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
