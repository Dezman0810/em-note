import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.user_contact import UserContact
from app.schemas.user_contact import UserContactCreate, UserContactRead, UserContactUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users/me/contacts", tags=["user-contacts"])

_CONTACTS_UNAVAILABLE = (
    "Не удалось обратиться к таблице контактов. Перезапустите API "
    "(при старте выполняется `alembic upgrade head`)."
)


def _missing_contacts_table(exc: ProgrammingError) -> bool:
    orig = getattr(exc, "orig", None)
    s = f"{exc} {(orig if orig else '')}".lower()
    if "user_contacts" not in s:
        return False
    return (
        "does not exist" in s
        or "undefined_table" in s.replace(" ", "")
        or "undefinedtable" in s.replace(" ", "")
        or "нет отношения" in s
    )


def _raise_contacts_db_if_missing_table(exc: ProgrammingError) -> None:
    if _missing_contacts_table(exc):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_CONTACTS_UNAVAILABLE,
        ) from exc


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@router.get("", response_model=list[UserContactRead])
async def list_user_contacts(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[UserContactRead]:
    try:
        result = await db.execute(
            select(UserContact)
            .where(UserContact.user_id == user.id)
            .order_by(UserContact.name.asc(), UserContact.email.asc())
        )
        rows = list(result.scalars().all())
        return [UserContactRead.model_validate(r) for r in rows]
    except ProgrammingError as e:
        logger.warning("user_contacts GET: %s", e)
        _raise_contacts_db_if_missing_table(e)
        raise


@router.post("", response_model=UserContactRead, status_code=status.HTTP_201_CREATED)
async def create_user_contact(
    body: UserContactCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> UserContactRead:
    name = body.name.strip()
    email = _normalize_email(str(body.email))
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите имя контакта")

    row = UserContact(user_id=user.id, name=name, email=email)
    db.add(row)
    try:
        await db.flush()
        await db.refresh(row)
        return UserContactRead.model_validate(row)
    except IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Контакт с таким email уже есть в вашей книге",
        ) from e
    except ProgrammingError as e:
        logger.exception("user_contacts POST: %s", e)
        _raise_contacts_db_if_missing_table(e)
        raise


@router.patch("/{contact_id}", response_model=UserContactRead)
async def update_user_contact(
    contact_id: uuid.UUID,
    body: UserContactUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> UserContactRead:
    try:
        row = (
            (
                await db.execute(
                    select(UserContact).where(
                        UserContact.id == contact_id,
                        UserContact.user_id == user.id,
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Контакт не найден")

        data = body.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            name = str(data["name"]).strip()
            if not name:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите имя контакта")
            row.name = name
        if "email" in data and data["email"] is not None:
            row.email = _normalize_email(str(data["email"]))

        await db.flush()
        await db.refresh(row)
        return UserContactRead.model_validate(row)
    except IntegrityError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Контакт с таким email уже есть в вашей книге",
        ) from e
    except ProgrammingError as e:
        logger.exception("user_contacts PATCH: %s", e)
        _raise_contacts_db_if_missing_table(e)
        raise


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_contact(
    contact_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    try:
        row = (
            (
                await db.execute(
                    select(UserContact).where(
                        UserContact.id == contact_id,
                        UserContact.user_id == user.id,
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Контакт не найден")
        await db.delete(row)
    except ProgrammingError as e:
        logger.exception("user_contacts DELETE: %s", e)
        _raise_contacts_db_if_missing_table(e)
        raise
