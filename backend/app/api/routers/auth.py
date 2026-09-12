from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.models.user import User
from app.schemas.user import Token, UserChangePassword, UserCreate, UserLogin, UserRead
from app.services.share_claim import claim_invite_shares_for_user
from app.services.share_recipient_tag import ensure_share_access_tags_for_user
from app.utils.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _email_key(email: str) -> str:
    return email.strip().lower()


def is_instance_owner_email(email_norm: str) -> bool:
    """Владелец инстанса: ему автоматически включены заметки, привычки и грамматика."""
    admin = (settings.admin_email or "").strip().lower()
    return bool(admin) and email_norm == admin


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    email_norm = _email_key(body.email)
    exists = await db.execute(select(User).where(func.lower(User.email) == email_norm))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    is_owner = is_instance_owner_email(email_norm)
    user = User(
        email=email_norm,
        password_hash=await hash_password(body.password),
        display_name=body.display_name or email_norm.split("@")[0],
        can_create_notes=is_owner,
        can_use_habits=is_owner,
        can_use_grammar=is_owner,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    await claim_invite_shares_for_user(db, user)
    await ensure_share_access_tags_for_user(db, user.id)
    return user


@router.post("/login", response_model=Token)
async def login(
    body: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    email_norm = _email_key(body.email)
    result = await db.execute(select(User).where(func.lower(User.email) == email_norm))
    user = result.scalar_one_or_none()
    if user is None or not await verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if is_instance_owner_email(_email_key(user.email)):
        if not user.can_create_notes:
            user.can_create_notes = True
        if not user.can_use_habits:
            user.can_use_habits = True
        if not user.can_use_grammar:
            user.can_use_grammar = True
        await db.flush()
    await claim_invite_shares_for_user(db, user)
    await ensure_share_access_tags_for_user(db, user.id)
    token = create_access_token(str(user.id))
    return Token(access_token=token)


@router.post("/change-password", response_model=UserRead)
async def change_password(
    body: UserChangePassword,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not await verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Текущий пароль неверный",
        )
    if body.new_password == body.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Новый пароль должен отличаться от временного",
        )
    user.password_hash = await hash_password(body.new_password)
    user.must_change_password = False
    await db.flush()
    await db.refresh(user)
    return user


@router.get("/me", response_model=UserRead)
async def me(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if is_instance_owner_email(_email_key(user.email)) and not user.can_use_grammar:
        user.can_use_grammar = True
        await db.flush()
    await claim_invite_shares_for_user(db, user)
    await ensure_share_access_tags_for_user(db, user.id)
    return user
