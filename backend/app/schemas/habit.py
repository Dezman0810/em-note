from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.utc_types import UtcDatetime

HabitMark = Literal["done", "missed", "clear"]


class HabitCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    icon: str = Field(default="", max_length=16)
    weekdays: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    target_days: int = Field(default=21, ge=1, le=60)
    starts_on: date | None = None


class HabitUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    icon: str | None = Field(default=None, max_length=16)
    weekdays: list[int] | None = None
    target_days: int | None = Field(default=None, ge=1, le=60)
    starts_on: date | None = None
    sort_order: int | None = Field(default=None, ge=1, le=999)


class HabitDayToggle(BaseModel):
    day: date | None = None
    status: HabitMark | None = None
    comment: str | None = Field(default=None, max_length=2000)


class HabitDayCellRead(BaseModel):
    day: date
    day_num: int
    weekday: int
    label: str
    is_today: bool
    is_anchor: bool
    state: str
    toggleable: bool
    comment: str = ""


class HabitRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    icon: str
    weekdays: list[int]
    target_days: int
    starts_on: date
    sort_order: int
    created_at: UtcDatetime
    updated_at: UtcDatetime
    today: date
    anchor: date
    done_count: int
    missed_count: int
    percent: int
    stage_emoji: str
    stage_label: str
    window_cells: list[HabitDayCellRead]
    slots: list[HabitDayCellRead]

    model_config = {"from_attributes": True}


class HabitPublicLinkRead(BaseModel):
    token: str
    created_at: UtcDatetime

    model_config = {"from_attributes": True}


class PublicHabitsPayload(BaseModel):
    owner_name: str
    habits: list[HabitRead]
    can_edit: bool = False
