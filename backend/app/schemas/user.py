import uuid

from pydantic import BaseModel, EmailStr, Field

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

    model_config = {"from_attributes": True}


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
