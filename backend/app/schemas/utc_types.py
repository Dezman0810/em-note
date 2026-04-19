"""Типы для дат в ответах API: всегда осмысленный UTC (наивные из БД считаем UTC)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import BeforeValidator


def ensure_utc_datetime(v: Any) -> Any:
    if v is None:
        return v
    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)
    return v


UtcDatetime = Annotated[datetime, BeforeValidator(ensure_utc_datetime)]
