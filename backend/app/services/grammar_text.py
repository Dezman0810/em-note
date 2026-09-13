"""Общие куски для проверки: UTF-16 смещения LanguageTool и найденные ошибки."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GrammarMatch:
    offset: int
    length: int
    message: str
    short_message: str
    replacements: list[str]
    issue_type: str


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def utf16_slice(text: str, start: int, end: int) -> str:
    raw = text.encode("utf-16-le")
    return raw[start * 2 : end * 2].decode("utf-16-le")


_LINE_END_OK = frozenset(".!?…:;)]}")
_REPEAT_HINTS = ("повтор", "тавтолог", "repeat", "duplicat", "twice")


def line_offsets(text: str) -> list[tuple[str, int]]:
    """Строка и её смещение в UTF-16 от начала текста."""
    start = 0
    parts = text.split("\n")
    out: list[tuple[str, int]] = []
    for i, line in enumerate(parts):
        out.append((line, start))
        start += utf16_len(line)
        if i < len(parts) - 1:
            start += 1
    return out


def close_line(line: str, has_following_break: bool = False) -> tuple[str, str]:
    """В конце фразы нужна точка, если её ещё нет — в том числе на последней строке."""
    del has_following_break
    raw = line.rstrip(" \t")
    if not raw or not any(ch.isalpha() for ch in raw):
        return line, "same"
    last = raw[-1]
    if last in _LINE_END_OK:
        return line, "same"
    suffix = line[len(raw) :]
    if last == ",":
        return raw[:-1] + "." + suffix, "replace_comma"
    return raw + "." + suffix, "add_period"


def close_lines(text: str) -> str:
    parts = text.split("\n")
    return "\n".join(
        close_line(line, i < len(parts) - 1)[0] for i, line in enumerate(parts)
    )


def line_end_matches(text: str) -> list[GrammarMatch]:
    """Точка в конце фразы, если её нет (каждая строка и конец выделения)."""
    matches: list[GrammarMatch] = []
    parts = text.split("\n")
    for i, (line, start) in enumerate(line_offsets(text)):
        closed, mode = close_line(line, i < len(parts) - 1)
        if mode == "same":
            continue
        raw = line.rstrip(" \t")
        if mode == "replace_comma":
            matches.append(
                GrammarMatch(
                    offset=start + utf16_len(raw) - 1,
                    length=1,
                    message="В конце предложения нужна точка, не запятая.",
                    short_message="Точка",
                    replacements=["."],
                    issue_type="typographical",
                )
            )
        else:
            matches.append(
                GrammarMatch(
                    offset=start + utf16_len(raw),
                    length=0,
                    message="В конце предложения нет точки.",
                    short_message="Точка",
                    replacements=["."],
                    issue_type="typographical",
                )
            )
        _ = closed
    return matches


def drop_duplicate_sentence_ends(
    existing: list[GrammarMatch],
    ends: list[GrammarMatch],
) -> list[GrammarMatch]:
    """Не ставить вторую точку, если LanguageTool уже закрыл фразу."""
    taken_ends: set[int] = set()
    covered: list[tuple[int, int]] = []
    for match in existing:
        if not match.replacements:
            continue
        repl = match.replacements[0]
        if repl and repl[-1] in ".!?…":
            taken_ends.add(match.offset + match.length)
        if match.length > 0:
            covered.append((match.offset, match.offset + match.length))
    out: list[GrammarMatch] = []
    for match in ends:
        if match.length == 0 and match.offset in taken_ends:
            continue
        if match.length > 0 and any(start <= match.offset < end for start, end in covered):
            continue
        out.append(match)
    return out


def text_for_languagetool(text: str) -> tuple[str, list[int]]:
    """Текст для LanguageTool: после каждой строки с переносом стоит точка.

    inserts — UTF-16 позиции в проверочном тексте, куда вставили точку.
    """
    closed_lines: list[str] = []
    inserts: list[int] = []
    check_at = 0
    parts = text.split("\n")
    for i, line in enumerate(parts):
        closed, mode = close_line(line, i < len(parts) - 1)
        if mode == "add_period":
            inserts.append(check_at + utf16_len(line.rstrip(" \t")))
        closed_lines.append(closed)
        check_at += utf16_len(closed)
        if i < len(parts) - 1:
            check_at += 1
    return "\n".join(closed_lines), inserts


def remap_match(match: GrammarMatch, inserts: list[int]) -> GrammarMatch | None:
    start, end = match.offset, match.offset + match.length
    inside = [p for p in inserts if start <= p < end]
    if match.length == 0:
        return None
    if inside and len(inside) == match.length:
        return None
    new_start = start - sum(1 for p in inserts if p < start)
    new_len = match.length - len(inside)
    if new_len <= 0:
        return None
    return GrammarMatch(
        offset=new_start,
        length=new_len,
        message=match.message,
        short_message=match.short_message,
        replacements=match.replacements,
        issue_type=match.issue_type,
    )


def is_cross_line_repeat(text: str, match: GrammarMatch) -> bool:
    """Одно и то же слово на разных строках — это не тавтология."""
    if match.length > 0:
        snippet = utf16_slice(text, match.offset, match.offset + match.length)
        if "\n" in snippet:
            return True
    blob = f"{match.message} {match.short_message} {match.issue_type}".lower()
    if not any(hint in blob for hint in _REPEAT_HINTS):
        return False
    before = utf16_slice(text, max(0, match.offset - 48), match.offset)
    return "\n" in before


def script_counts(text: str) -> tuple[int, int]:
    cyr = sum(1 for ch in text if "а" <= ch.lower() <= "я" or ch.lower() == "ё")
    lat = sum(1 for ch in text if "a" <= ch.lower() <= "z")
    return cyr, lat


def languages_for_text(text: str) -> list[str]:
    cyr, lat = script_counts(text)
    langs: list[str] = []
    if cyr >= 2:
        langs.append("ru-RU")
    if lat >= 3:
        langs.append("en-US")
    if not langs:
        langs.append("auto")
    return langs


def utf16_replace(text: str, offset: int, length: int, replacement: str) -> str:
    raw = text.encode("utf-16-le")
    start = offset * 2
    end = (offset + length) * 2
    if start < 0 or end > len(raw) or start > end:
        return text
    return (raw[:start] + replacement.encode("utf-16-le") + raw[end:]).decode("utf-16-le")
