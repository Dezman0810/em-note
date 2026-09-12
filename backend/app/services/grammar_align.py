"""Выравнивание старого и нового текста для подсветки правок."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.schemas.grammar import GrammarChange, GrammarSegment
from app.services.grammar_text import GrammarMatch, utf16_len, utf16_slice

_TOKEN_RE = re.compile(r"\s+|[^\W_]+|[^\s]", re.UNICODE)


def classify_issue(match: GrammarMatch) -> str:
    issue = match.issue_type.lower()
    blob = f"{match.message} {match.short_message}".lower()
    if issue == "misspelling" or "орфограф" in blob or "spelling" in blob:
        return "spelling"
    if (
        issue in {"typographical", "typographicalconfusion"}
        or "запят" in blob
        or "comma" in blob
        or "пунктуа" in blob
    ):
        return "punctuation"
    if issue in {"style", "register", "locale-violation"}:
        return "style"
    return "grammar"


def _seg(text: str, kind: str = "ok", message: str = "", before: str = "", after: str = "") -> GrammarSegment:
    return GrammarSegment(text=text, kind=kind, message=message, before=before, after=after)


def _nonoverlap(matches: list[GrammarMatch]) -> list[GrammarMatch]:
    ordered = sorted(matches, key=lambda m: (m.offset, -m.length))
    kept: list[GrammarMatch] = []
    cursor = 0
    for match in ordered:
        if match.offset < cursor:
            continue
        kept.append(match)
        cursor = match.offset + match.length
    return kept


def build_match_parts(
    text: str,
    matches: list[GrammarMatch],
    replacement_index: int = 0,
) -> tuple[list[GrammarSegment], list[GrammarSegment], list[GrammarChange]]:
    """Слева ошибочные фрагменты, справа те же места после замены."""
    orig: list[GrammarSegment] = []
    rev: list[GrammarSegment] = []
    changes: list[GrammarChange] = []
    cursor = 0
    end = utf16_len(text)
    for match in _nonoverlap(matches):
        if match.offset > cursor:
            chunk = utf16_slice(text, cursor, match.offset)
            if chunk:
                orig.append(_seg(chunk))
                rev.append(_seg(chunk))
        before = utf16_slice(text, match.offset, match.offset + match.length)
        after = before
        if match.replacements:
            after = match.replacements[min(replacement_index, len(match.replacements) - 1)]
        note = match.short_message or match.message
        kind = classify_issue(match)
        if before:
            orig.append(_seg(before, "error", note, before, after))
        if after:
            rev.append(_seg(after, "fix" if after != before else "ok", note, before, after))
        if before != after:
            changes.append(GrammarChange(before=before, after=after, message=note, kind=kind))
        cursor = match.offset + match.length
    if cursor < end:
        tail = utf16_slice(text, cursor, end)
        if tail:
            orig.append(_seg(tail))
            rev.append(_seg(tail))
    if not orig:
        orig.append(_seg(text))
        rev.append(_seg(text))
    return orig, rev, changes


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def build_diff_parts(
    original: str,
    revised: str,
) -> tuple[list[GrammarSegment], list[GrammarSegment], list[GrammarChange]]:
    """Подсветка любых правок, включая перестановку слов и новые формулировки."""
    left = tokenize(original)
    right = tokenize(revised)
    orig: list[GrammarSegment] = []
    rev: list[GrammarSegment] = []
    changes: list[GrammarChange] = []
    matcher = SequenceMatcher(a=left, b=right, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old = "".join(left[i1:i2])
        new = "".join(right[j1:j2])
        if tag == "equal":
            if old:
                orig.append(_seg(old))
                rev.append(_seg(new))
            continue
        if tag == "replace":
            if old:
                orig.append(_seg(old, "error", "формулировка", old, new))
            if new:
                rev.append(_seg(new, "fix", "формулировка", old, new))
            if old.strip() or new.strip():
                changes.append(
                    GrammarChange(
                        before=old.strip(),
                        after=new.strip(),
                        message="формулировка",
                        kind="rewrite",
                    )
                )
            continue
        if tag == "delete" and old:
            orig.append(_seg(old, "error", "удалено", old, ""))
            if old.strip():
                changes.append(GrammarChange(before=old.strip(), after="", message="удалено", kind="rewrite"))
            continue
        if tag == "insert" and new:
            rev.append(_seg(new, "fix", "добавлено", "", new))
            if new.strip():
                changes.append(GrammarChange(before="", after=new.strip(), message="добавлено", kind="rewrite"))
    if not orig:
        orig.append(_seg(original))
    if not rev:
        rev.append(_seg(revised))
    return orig, rev, changes
