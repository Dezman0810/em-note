from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserLogin, UserRead
from app.utils.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _email_key(email: str) -> str:
    return email.strip().lower()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    email_norm = _email_key(body.email)
    exists = await db.execute(select(User).where(func.lower(User.email) == email_norm))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    is_owner = bool(settings.admin_email) and email_norm == settings.admin_email.strip().lower()
    user = User(
        email=email_norm,
        password_hash=hash_password(body.password),
        display_name=body.display_name or email_norm.split("@")[0],
        can_create_notes=is_owner,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    body: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    email_norm = _email_key(body.email)
    result = await db.execute(select(User).where(func.lower(User.email) == email_norm))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    admin_e = settings.admin_email.strip().lower() if settings.admin_email else ""
    if admin_e and user.email.strip().lower() == admin_e and not user.can_create_notes:
        user.can_create_notes = True
        await db.flush()
    token = create_access_token(str(user.id))
    return Token(access_token=token)


@router.get("/me", response_model=UserRead)
async def me(user: Annotated[User, Depends(get_current_user)]) -> User:
    return user
