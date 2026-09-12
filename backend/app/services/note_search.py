"""Предикат поиска заметок по тексту.

Полнотекстовая часть работает по generated-колонке `notes.search_vector`
(GIN-индекс ix_notes_search_vector, миграция 001_initial). Колонка не описана в
модели Note намеренно: она вычисляется Postgres и не должна попадать в INSERT
или в SELECT списков.
"""

import re

from sqlalchemy import ColumnElement, func, literal_column
from sqlalchemy.dialects.postgresql import TSVECTOR

from app.models.note import Note

# Та же конфигурация, что в определении search_vector: без стемминга и стоп-слов.
_TS_CONFIG = "simple"
_SEARCH_VECTOR = literal_column("notes.search_vector", type_=TSVECTOR)

# Слово = буквы/цифры. Отбрасывая всё остальное, гарантируем, что в to_tsquery
# не попадут его операторы (& | ! : * скобки).
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _ilike_pattern(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


# Короткий префикс вроде «ест:*» цепляет слишком много слов (есть, естественно)
# и выглядит как «нашло Проекты». Начало слова оставляем от 4 букв («прив» → привычка).
_PREFIX_MIN_LEN = 4


def _prefix_tsquery(q: str) -> str | None:
    """«прив выч» → «прив:* & выч:*»; None, если нет слов достаточной длины."""
    tokens = [t for t in _WORD_RE.findall(q.lower()) if len(t) >= _PREFIX_MIN_LEN]
    if not tokens:
        return None
    return " & ".join(f"{token}:*" for token in tokens)


def note_search_predicate(q: str) -> ColumnElement[bool]:
    """Подстрока в заголовке и тексте + префикс слова от 4 букв по search_vector.

    «ест» находит «есть» и «месте», но не «Проекты» (там «ект», не «ест»).
    «прив» по-прежнему находит «привычка» через полнотекстовый префикс.
    """
    pattern = _ilike_pattern(q)
    substring = Note.title.ilike(pattern, escape="\\") | Note.content_plain.ilike(
        pattern, escape="\\"
    )
    tsquery = _prefix_tsquery(q)
    if tsquery is None:
        return substring
    full_text = _SEARCH_VECTOR.bool_op("@@")(func.to_tsquery(_TS_CONFIG, tsquery))
    return full_text | substring
