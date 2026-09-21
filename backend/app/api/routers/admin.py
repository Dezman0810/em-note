import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.config import settings
from app.models.user import User
from app.schemas.user import UserAdminListItem, UserAdminPasswordReset, UserAdminUpdate
from app.utils.security import generate_temporary_password, hash_password

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserAdminListItem])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[User, Depends(require_admin)],
) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


@router.patch("/users/{user_id}", response_model=UserAdminListItem)
async def patch_user_access(
    user_id: uuid.UUID,
    body: UserAdminUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[User, Depends(require_admin)],
) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    a = (settings.admin_email or "").strip().lower()
    is_admin_user = bool(a) and user.email.strip().lower() == a
    if is_admin_user and body.can_create_notes is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя отключить создание заметок у аккаунта администратора",
        )
    if body.can_create_notes is not None:
        user.can_create_notes = body.can_create_notes
    if body.can_use_habits is not None:
        user.can_use_habits = body.can_use_habits
    if body.can_use_grammar is not None:
        user.can_use_grammar = body.can_use_grammar
    if body.can_use_budget is not None:
        user.can_use_budget = body.can_use_budget
    if body.can_use_schemas is not None:
        user.can_use_schemas = body.can_use_schemas
    if body.can_export_schemas is not None:
        user.can_export_schemas = body.can_export_schemas
    if body.can_export_mindmaps is not None:
        user.can_export_mindmaps = body.can_export_mindmaps
    if body.can_export_diagrams is not None:
        user.can_export_diagrams = body.can_export_diagrams
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/users/{user_id}/reset-password", response_model=UserAdminPasswordReset)
async def reset_user_password(
    user_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[User, Depends(require_admin)],
) -> UserAdminPasswordReset:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    temporary = generate_temporary_password()
    user.password_hash = await hash_password(temporary)
    user.must_change_password = True
    await db.flush()
    return UserAdminPasswordReset(email=user.email, temporary_password=temporary)
