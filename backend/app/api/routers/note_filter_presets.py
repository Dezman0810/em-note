import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.user_note_filter_preset import UserNoteFilterPreset
from app.schemas.note_filter_preset import FilterPresetCreate, FilterPresetRead, FilterPresetUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/note-filter-presets", tags=["note-filter-presets"])

_PRESETS_UNAVAILABLE = (
    "Не удалось обратиться к таблице наборов фильтров. Перезапустите API "
    "(при старте выполняется `alembic upgrade head`). "
    "Если ошибка остаётся — проверьте DATABASE_URL или выполните вручную: "
    "`cd backend && alembic upgrade head`."
)


def _ids_to_rows(ids: list[uuid.UUID]) -> list[str]:
    return [str(u) for u in ids]


def _missing_filter_presets_table(exc: ProgrammingError) -> bool:
    """Типично: таблица не создана (миграция 202605211400 не применена)."""
    orig = getattr(exc, "orig", None)
    s = f"{exc} {(orig if orig else '')}".lower()
    if "user_note_filter_presets" not in s:
        return False
    return (
        "does not exist" in s
        or "undefined_table" in s.replace(" ", "")
        or "undefinedtable" in s.replace(" ", "")
        or "нет отношения" in s
    )


def _raise_presets_db_if_missing_table(exc: ProgrammingError) -> None:
    if _missing_filter_presets_table(exc):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_PRESETS_UNAVAILABLE,
        ) from exc


@router.get("", response_model=list[FilterPresetRead])
async def list_presets(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[FilterPresetRead]:
    try:
        result = await db.execute(
            select(UserNoteFilterPreset)
            .where(UserNoteFilterPreset.user_id == user.id)
            .order_by(UserNoteFilterPreset.sort_order.asc(), UserNoteFilterPreset.name.asc())
        )
        rows = list(result.scalars().all())
        return [FilterPresetRead.model_validate(r) for r in rows]
    except ProgrammingError as e:
        logger.warning("note_filter_presets GET: %s", e)
        _raise_presets_db_if_missing_table(e)
        raise


@router.post("", response_model=FilterPresetRead, status_code=status.HTTP_201_CREATED)
async def create_preset(
    body: FilterPresetCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> FilterPresetRead:
    try:
        max_so_raw = (
            await db.execute(
                select(func.coalesce(func.max(UserNoteFilterPreset.sort_order), -1)).where(
                    UserNoteFilterPreset.user_id == user.id
                )
            )
        ).scalar_one()
        next_so = int(max_so_raw) + 1

        row = UserNoteFilterPreset(
            user_id=user.id,
            name=body.name.strip(),
            search_query=(body.search_query.strip() or None if body.search_query else None),
            folder_ids=_ids_to_rows(body.folder_ids),
            exclude_folder_ids=_ids_to_rows(body.exclude_folder_ids),
            tag_ids=_ids_to_rows(body.tag_ids),
            exclude_tag_ids=_ids_to_rows(body.exclude_tag_ids),
            exclude_tag_undo_ids=_ids_to_rows(body.exclude_tag_undo_ids),
            conjunct_tag_ids=_ids_to_rows(body.conjunct_tag_ids),
            tag_nav_collapsed_ids=_ids_to_rows(body.tag_nav_collapsed_ids),
            tag_match_all=body.tag_match_all,
            sort_order=next_so,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return FilterPresetRead.model_validate(row)
    except ProgrammingError as e:
        logger.exception("note_filter_presets POST: %s", e)
        _raise_presets_db_if_missing_table(e)
        raise


@router.patch("/{preset_id}", response_model=FilterPresetRead)
async def patch_preset(
    preset_id: uuid.UUID,
    body: FilterPresetUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> FilterPresetRead:
    try:
        row = (
            (
                await db.execute(
                    select(UserNoteFilterPreset).where(
                        UserNoteFilterPreset.id == preset_id,
                        UserNoteFilterPreset.user_id == user.id,
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Набор не найден")

        data = body.model_dump(exclude_unset=True)
        if "name" in data and data["name"] is not None:
            row.name = data["name"].strip()

        if "search_query" in data:
            sq = data["search_query"]
            if sq is None:
                row.search_query = None
            else:
                t = str(sq).strip()
                row.search_query = t or None

        for key_src, attr in (
            ("folder_ids", "folder_ids"),
            ("exclude_folder_ids", "exclude_folder_ids"),
            ("tag_ids", "tag_ids"),
            ("exclude_tag_ids", "exclude_tag_ids"),
            ("exclude_tag_undo_ids", "exclude_tag_undo_ids"),
            ("conjunct_tag_ids", "conjunct_tag_ids"),
            ("tag_nav_collapsed_ids", "tag_nav_collapsed_ids"),
        ):
            if key_src not in data:
                continue
            val = data[key_src]
            if val is None:
                setattr(row, attr, [])
            elif isinstance(val, list):
                setattr(row, attr, _ids_to_rows(val))

        if "tag_match_all" in data:
            row.tag_match_all = bool(data["tag_match_all"])

        await db.flush()
        await db.refresh(row)
        return FilterPresetRead.model_validate(row)
    except ProgrammingError as e:
        logger.exception("note_filter_presets PATCH: %s", e)
        _raise_presets_db_if_missing_table(e)
        raise


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset(
    preset_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    try:
        row = (
            (
                await db.execute(
                    select(UserNoteFilterPreset).where(
                        UserNoteFilterPreset.id == preset_id,
                        UserNoteFilterPreset.user_id == user.id,
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Набор не найден")
        await db.delete(row)
    except ProgrammingError as e:
        logger.exception("note_filter_presets DELETE: %s", e)
        _raise_presets_db_if_missing_table(e)
        raise

