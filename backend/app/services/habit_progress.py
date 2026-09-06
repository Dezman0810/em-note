"""Привычки: дни недели, N повторений, календарь якоря ±10 дней."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    MSK = ZoneInfo("Europe/Moscow")
except ZoneInfoNotFoundError:
    MSK = timezone(timedelta(hours=3))

WEEKDAY_LABELS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
WINDOW_RADIUS = 10

SMILES: list[tuple[int, str, str]] = [
    (0, "🙂", "Улыбка"),
    (17, "😊", "Тепло"),
    (34, "😄", "Радость"),
    (50, "😁", "Широко"),
    (67, "🥰", "Сияю"),
    (84, "🥳", "Праздник"),
    (100, "🤩", "Вау!"),
]


def today_msk(now: datetime | None = None) -> date:
    stamp = now if now is not None else datetime.now(MSK)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(MSK).date()


def parse_anchor(raw: str | None, today: date) -> date:
    if not raw:
        return today
    try:
        y_s, m_s, d_s = raw.strip().split("-", 2)
        y, m, d = int(y_s), int(m_s), int(d_s)
        return date(y, m, d)
    except ValueError:
        return today


def normalize_weekdays(raw: list[int] | None) -> list[int]:
    return sorted({int(x) for x in (raw or []) if 1 <= int(x) <= 7})


def smile_for_percent(percent: int) -> tuple[str, str]:
    pct = max(0, min(100, int(percent)))
    chosen = SMILES[0]
    for bound, emo, lab in SMILES:
        if pct >= bound:
            chosen = (bound, emo, lab)
    return chosen[1], chosen[2]


def slot_percent(done_count: int, target: int) -> int:
    if target <= 0:
        return 0
    return max(0, min(100, round(100 * done_count / target)))


def habit_slots(weekdays: list[int], count: int, start: date) -> list[date]:
    """Ближайшие `count` выбранных дней недели начиная с start (включительно)."""
    if not weekdays or count < 1:
        return []
    out: list[date] = []
    cur = start
    guard = 0
    while len(out) < count and guard < 900:
        if cur.isoweekday() in weekdays:
            out.append(cur)
        cur += timedelta(days=1)
        guard += 1
    return out


@dataclass(frozen=True)
class DayCell:
    day: date
    day_num: int
    weekday: int
    label: str
    is_today: bool
    is_anchor: bool
    state: str
    toggleable: bool
    comment: str = ""


def window_cells(anchor: date, today: date) -> list[DayCell]:
    cells: list[DayCell] = []
    for i in range(-WINDOW_RADIUS, WINDOW_RADIUS + 1):
        d = anchor + timedelta(days=i)
        cells.append(
            DayCell(
                day=d,
                day_num=d.day,
                weekday=d.isoweekday(),
                label=WEEKDAY_LABELS[d.isoweekday() - 1],
                is_today=d == today,
                is_anchor=i == 0,
                state="anchor" if i == 0 else "empty",
                toggleable=True,
            )
        )
    return cells


def slot_cells(
    slots: list[date],
    marks: dict[date, str],
    today: date,
    comments: dict[date, str] | None = None,
) -> list[DayCell]:
    notes = comments or {}
    cells: list[DayCell] = []
    for d in slots:
        raw = marks.get(d)
        if raw == "done":
            state = "done"
        elif raw == "missed":
            state = "missed"
        else:
            state = "empty"
        cells.append(
            DayCell(
                day=d,
                day_num=d.day,
                weekday=d.isoweekday(),
                label=WEEKDAY_LABELS[d.isoweekday() - 1],
                is_today=d == today,
                is_anchor=False,
                state=state,
                toggleable=True,
                comment=(notes.get(d) or "").strip(),
            )
        )
    return cells
