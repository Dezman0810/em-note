"""ETag / Cache-Control: условные запросы вместо повторной отдачи тела."""

import hashlib

# Вложения не меняются: storage_key уникален на файл, перезаписи нет.
IMMUTABLE_CACHE_CONTROL = "private, max-age=31536000, immutable"
# Публичные данные меняются в любой момент — только валидация по ETag.
REVALIDATE_CACHE_CONTROL = "private, max-age=0, must-revalidate"


def make_etag(*parts: object) -> str:
    """Сильный ETag из полей, меняющихся вместе с содержимым."""
    raw = "|".join("" if p is None else str(p) for p in parts)
    return '"' + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32] + '"'


def etag_matches(if_none_match: str | None, etag: str) -> bool:
    """Разбор If-None-Match: список тегов, `*`, слабые префиксы W/."""
    if not if_none_match:
        return False
    bare = etag.strip('"')
    for raw in if_none_match.split(","):
        candidate = raw.strip()
        if candidate == "*":
            return True
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate.strip('"') == bare:
            return True
    return False
