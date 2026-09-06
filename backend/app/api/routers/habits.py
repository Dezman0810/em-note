import secrets
import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_habits_access
from app.database import get_db
from app.models.habit import Habit, HabitCheck
from app.models.habit_public_link import HabitPublicLink
from app.models.user import User
from app.schemas.habit import (
    HabitCreate,
    HabitDayCellRead,
    HabitDayToggle,
    HabitPublicLinkRead,
    HabitRead,
    HabitUpdate,
)
from app.services.habit_progress import (
    habit_slots,
    normalize_weekdays,
    parse_anchor,
    slot_cells,
    slot_percent,
    smile_for_percent,
    today_msk,
    window_cells,
)

router = APIRouter(prefix="/habits", tags=["habits"])


def _as_date(v: date | datetime) -> date:
    return v.date() if isinstance(v, datetime) else v


def _marks_and_comments(habit: Habit) -> tuple[dict[date, str], dict[date, str]]:
    marks: dict[date, str] = {}
    comments: dict[date, str] = {}
    for c in habit.checks:
        day = _as_date(c.day)
        st = (c.status or "").strip().lower()
        if st in ("done", "missed"):
            marks[day] = st
        note = (getattr(c, "comment", None) or "").strip()
        if note:
            comments[day] = note
    return marks, comments


def _habit_starts_on(habit: Habit, today: date) -> date:
    raw = getattr(habit, "starts_on", None)
    if raw is not None:
        return _as_date(raw)
    return today_msk(habit.created_at) if habit.created_at is not None else today


def _to_read(habit: Habit, today: date, view: date) -> HabitRead:
    weekdays = normalize_weekdays(list(habit.weekdays or []))
    target = max(1, int(habit.target_days or 1))
    marks, comments = _marks_and_comments(habit)
    starts = _habit_starts_on(habit, today)
    slots = habit_slots(weekdays, target, starts)
    cells = slot_cells(slots, marks, today, comments)
    done_count = sum(1 for c in cells if c.state == "done")
    missed_count = sum(1 for c in cells if c.state == "missed")
    percent = slot_percent(done_count, target)
    emoji, label = smile_for_percent(percent)
    return HabitRead(
        id=habit.id,
        user_id=habit.user_id,
        title=habit.title,
        icon=habit.icon or "",
        weekdays=weekdays,
        target_days=target,
        starts_on=starts,
        sort_order=habit.sort_order,
        created_at=habit.created_at,
        updated_at=habit.updated_at,
        today=today,
        anchor=view,
        done_count=done_count,
        missed_count=missed_count,
        percent=percent,
        stage_emoji=emoji,
        stage_label=label,
        window_cells=[HabitDayCellRead.model_validate(c, from_attributes=True) for c in window_cells(view, today)],
        slots=[HabitDayCellRead.model_validate(c, from_attributes=True) for c in cells],
    )


async def _load_habit(db: AsyncSession, habit_id: uuid.UUID, user_id: uuid.UUID) -> Habit:
    row = (
        (
            await db.execute(
                select(Habit)
                .options(selectinload(Habit.checks))
                .where(Habit.id == habit_id, Habit.user_id == user_id)
            )
        )
        .scalars()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Привычка не найдена")
    return row


def _new_share_token() -> str:
    return secrets.token_urlsafe(32)


async def habits_for_owner(db: AsyncSession, user_id: uuid.UUID, anchor: str | None) -> list[HabitRead]:
    today = today_msk()
    start = parse_anchor(anchor, today)
    result = await db.execute(
        select(Habit)
        .options(selectinload(Habit.checks))
        .where(Habit.user_id == user_id)
        .order_by(Habit.sort_order.asc(), Habit.created_at.asc())
    )
    return [_to_read(h, today, start) for h in result.scalars().unique().all()]


@router.get("/public-link", response_model=HabitPublicLinkRead)
async def get_habit_public_link(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_habits_access)],
) -> HabitPublicLink:
    row = (
        (await db.execute(select(HabitPublicLink).where(HabitPublicLink.user_id == user.id)))
        .scalars()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не создана")
    return row


@router.put("/public-link", response_model=HabitPublicLinkRead)
async def create_habit_public_link(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_habits_access)],
) -> HabitPublicLink:
    row = (
        (await db.execute(select(HabitPublicLink).where(HabitPublicLink.user_id == user.id)))
        .scalars()
        .one_or_none()
    )
    if row is None:
        row = HabitPublicLink(user_id=user.id, token=_new_share_token())
        db.add(row)
        await db.flush()
        await db.refresh(row)
    return row


@router.delete("/public-link", status_code=status.HTTP_204_NO_CONTENT)
async def delete_habit_public_link(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_habits_access)],
) -> None:
    row = (
        (await db.execute(select(HabitPublicLink).where(HabitPublicLink.user_id == user.id)))
        .scalars()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ссылка не создана")
    await db.delete(row)


@router.get("", response_model=list[HabitRead])
async def list_habits(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_habits_access)],
    anchor: Annotated[str | None, Query()] = None,
) -> list[HabitRead]:
    return await habits_for_owner(db, user.id, anchor)


@router.post("", response_model=HabitRead, status_code=status.HTTP_201_CREATED)
async def create_habit(
    body: HabitCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_habits_access)],
    anchor: Annotated[str | None, Query()] = None,
) -> HabitRead:
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите название")
    weekdays = normalize_weekdays(body.weekdays)
    if not weekdays:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Выберите хотя бы один день недели")
    max_ord = (
        await db.execute(select(func.coalesce(func.max(Habit.sort_order), 0)).where(Habit.user_id == user.id))
    ).scalar_one()
    today = today_msk()
    starts_on = body.starts_on or parse_anchor(anchor, today)
    row = Habit(
        user_id=user.id,
        title=title,
        icon=(body.icon or "").strip()[:16],
        weekdays=weekdays,
        target_days=body.target_days,
        starts_on=starts_on,
        sort_order=int(max_ord) + 1,
    )
    db.add(row)
    await db.flush()
    loaded = await _load_habit(db, row.id, user.id)
    return _to_read(loaded, today, parse_anchor(anchor, today))


@router.patch("/{habit_id}", response_model=HabitRead)
async def update_habit(
    habit_id: uuid.UUID,
    body: HabitUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_habits_access)],
    anchor: Annotated[str | None, Query()] = None,
) -> HabitRead:
    row = await _load_habit(db, habit_id, user.id)
    data = body.model_dump(exclude_unset=True)
    if "title" in data and data["title"] is not None:
        title = str(data["title"]).strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите название")
        row.title = title
    if "icon" in data and data["icon"] is not None:
        row.icon = str(data["icon"]).strip()[:16]
    if "weekdays" in data and data["weekdays"] is not None:
        weekdays = normalize_weekdays(list(data["weekdays"]))
        if not weekdays:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Выберите хотя бы один день недели")
        row.weekdays = weekdays
    if "target_days" in data and data["target_days"] is not None:
        row.target_days = int(data["target_days"])
    if "starts_on" in data and data["starts_on"] is not None:
        row.starts_on = data["starts_on"]
    if "sort_order" in data and data["sort_order"] is not None:
        row.sort_order = int(data["sort_order"])
    await db.flush()
    today = today_msk()
    loaded = await _load_habit(db, row.id, user.id)
    return _to_read(loaded, today, parse_anchor(anchor, today))


@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_habit(
    habit_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_habits_access)],
) -> None:
    row = await _load_habit(db, habit_id, user.id)
    await db.delete(row)


@router.put("/{habit_id}/day", response_model=HabitRead)
async def toggle_habit_day(
    habit_id: uuid.UUID,
    body: HabitDayToggle,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_habits_access)],
    anchor: Annotated[str | None, Query()] = None,
) -> HabitRead:
    today = today_msk()
    day = body.day or today
    if body.status is None and body.comment is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите отметку или комментарий")
    row = await _load_habit(db, habit_id, user.id)
    existing = next((c for c in row.checks if _as_date(c.day) == day), None)
    kept = (existing.comment if existing is not None else "") or ""
    if body.comment is not None:
        kept = body.comment.strip()[:2000]
    want = body.status
    if want == "clear":
        if existing is None:
            pass
        elif kept:
            existing.status = "none"
            existing.comment = kept
            await db.flush()
        else:
            row.checks.remove(existing)
            await db.delete(existing)
            await db.flush()
    elif want in ("done", "missed"):
        if existing is None:
            row.checks.append(HabitCheck(habit_id=row.id, day=day, status=want, comment=kept))
        else:
            existing.status = want
            existing.comment = kept
        await db.flush()
    elif body.comment is not None:
        if existing is None:
            if kept:
                row.checks.append(HabitCheck(habit_id=row.id, day=day, status="none", comment=kept))
                await db.flush()
        else:
            existing.comment = kept
            st = (existing.status or "").strip().lower()
            if not kept and st not in ("done", "missed"):
                row.checks.remove(existing)
                await db.delete(existing)
            await db.flush()
    await db.refresh(row, attribute_names=["checks"])
    return _to_read(row, today, parse_anchor(anchor, today))
