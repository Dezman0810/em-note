"""Проверка орфографии, пунктуации и грамматики через LanguageTool.

Русский и английский: для смешанного текста проверяем оба языка.
Стилистику и переформулировку не предлагаем.
"""

from __future__ import annotations

import httpx

from dataclasses import replace

from app.config import settings
from app.schemas.grammar import (
    GRAMMAR_MAX_CHARS,
    GrammarAdvice,
    GrammarCheckResponse,
    GrammarIssue,
    GrammarSuggestion,
)
from app.services.grammar_align import build_diff_parts, build_match_parts
from app.services.grammar_text import (
    GrammarMatch,
    is_cross_line_repeat,
    languages_for_text,
    drop_duplicate_sentence_ends,
    line_end_matches,
    remap_match,
    text_for_languagetool,
    utf16_replace,
    utf16_slice,
)

_STYLE_ISSUE_TYPES = frozenset({"style", "register"})

_USER_AGENT = "em-note-grammar/1.0 (local notes; LanguageTool client)"
_TIMEOUT_SEC = 20.0
_MAX_REPLACEMENTS = 5
_MAX_ISSUES = 80
_COMMON_TYPOS = {
    frozenset("тч"),
    frozenset("ао"),
    frozenset("ие"),
    frozenset("шщ"),
    frozenset("ыи"),
    frozenset("ьъ"),
    frozenset("её"),
    frozenset("бп"),
    frozenset("зс"),
    frozenset("жш"),
}


def _edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    prev = list(range(len(right) + 1))
    for i, ca in enumerate(left, 1):
        cur = [i]
        for j, cb in enumerate(right, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _typo_distance(original: str, replacement: str) -> float:
    src = original.casefold()
    dst = replacement.casefold()
    if len(src) == len(dst):
        penalty = 0.0
        for ca, cb in zip(src, dst):
            if ca == cb:
                continue
            penalty += 0.45 if frozenset((ca, cb)) in _COMMON_TYPOS else 1.0
        return penalty
    return float(_edit_distance(src, dst))


def _norm_word(value: str) -> str:
    return value.casefold().replace("ё", "е").strip(" \t.,!?;:()[]«»\"'")


def _stem(value: str) -> str:
    text = _norm_word(value)
    for ending in (
        "ами",
        "ями",
        "ого",
        "ему",
        "ыми",
        "ими",
        "ах",
        "ях",
        "ов",
        "ев",
        "ей",
        "ой",
        "ий",
        "ый",
        "ая",
        "ое",
        "ые",
        "ую",
        "ам",
        "ям",
        "ом",
        "ем",
        "у",
        "а",
        "е",
        "ы",
        "и",
        "о",
        "й",
        "ь",
    ):
        if len(text) > len(ending) + 2 and text.endswith(ending):
            return text[: -len(ending)]
    return text


# Не подставлять чужие термины и инфинитив вместо личной формы.
_BLOCKED_STEMS: dict[str, frozenset[str]] = {
    "отчет": frozenset({"смет"}),
    "смет": frozenset({"отчет"}),
    "мог": frozenset({"моч"}),
    "моч": frozenset({"мог"}),
}


def _alnum_key(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum()).casefold().replace("ё", "е")


def is_punctuation_edit(original: str, replacement: str) -> bool:
    """Запятая, точка, пробел — да. Другое слово (могу → мочь) — нет."""
    if original == replacement:
        return False
    return _alnum_key(original) == _alnum_key(replacement)


def match_slice(text: str, match: GrammarMatch) -> str:
    if match.length <= 0:
        return ""
    return utf16_slice(text, match.offset, match.offset + match.length)


def punctuation_replacements(text: str, match: GrammarMatch) -> list[str]:
    current = match_slice(text, match)
    return [item for item in match.replacements if is_punctuation_edit(current, item)]


def is_punctuation_match(text: str, match: GrammarMatch) -> bool:
    return bool(punctuation_replacements(text, match))


def punctuation_matches(text: str, matches: list[GrammarMatch]) -> list[GrammarMatch]:
    out: list[GrammarMatch] = []
    for match in matches:
        punct = punctuation_replacements(text, match)
        if punct:
            out.append(replace(match, replacements=punct))
    return out


def advice_from_matches(text: str, matches: list[GrammarMatch]) -> list[GrammarAdvice]:
    out: list[GrammarAdvice] = []
    seen: set[tuple[str, str]] = set()
    for match in matches:
        if is_punctuation_match(text, match):
            continue
        current = match_slice(text, match)
        options = [item for item in match.replacements if item and item != current]
        if not current or not options:
            continue
        options = sorted(
            options,
            key=lambda item: (
                not is_safe_replacement(current, item),
                _typo_distance(current, item),
                abs(len(item) - len(current)),
            ),
        )
        key = (current, options[0])
        if key in seen:
            continue
        seen.add(key)
        out.append(
            GrammarAdvice(
                before=current,
                after=options[0],
                message=match.short_message or match.message,
                options=options[:_MAX_REPLACEMENTS],
            )
        )
    return out


def is_safe_replacement(original: str, replacement: str) -> bool:
    """Опечатка и запятая — да; другое слово с другим смыслом — нет."""
    src = _norm_word(original)
    dst = _norm_word(replacement)
    if not src or not dst or src == dst:
        return True
    if src in dst or dst in src:
        return _edit_distance(src, dst) <= 3
    src_stem, dst_stem = _stem(src), _stem(dst)
    for stem, blocked in _BLOCKED_STEMS.items():
        if src_stem.startswith(stem) and any(dst_stem.startswith(item) for item in blocked):
            return False
    if _typo_distance(src, dst) <= 1.5:
        return True
    if src_stem[:2] == dst_stem[:2] and _edit_distance(src, dst) <= 2:
        return True
    if len(src) <= 4 and _edit_distance(src, dst) > 1:
        return False
    if src_stem[:3] != dst_stem[:3] and _edit_distance(src, dst) > 2:
        return False
    return True


def rank_replacements(original: str, replacements: list[str]) -> list[str]:
    """Ближайшая безопасная замена — первой. Чужие слова вроде «сметы» отбрасываем."""
    safe = [item for item in replacements if is_safe_replacement(original, item)]
    return sorted(
        safe,
        key=lambda item: (_typo_distance(original, item), abs(len(item) - len(original))),
    )


def apply_matches(text: str, matches: list[GrammarMatch], replacement_index: int = 0) -> str:
    """Применяет замены с конца, чтобы смещения LanguageTool (UTF-16) остались верными."""
    result = text
    ordered = sorted(matches, key=lambda m: (m.offset, m.length), reverse=True)
    for match in ordered:
        if not match.replacements:
            continue
        idx = min(replacement_index, len(match.replacements) - 1)
        result = utf16_replace(result, match.offset, match.length, match.replacements[idx])
    return result


def _effective_changes(text: str, matches: list[GrammarMatch], replacement_index: int) -> int:
    n = 0
    for match in matches:
        if not match.replacements:
            continue
        idx = min(replacement_index, len(match.replacements) - 1)
        current = utf16_slice(text, match.offset, match.offset + match.length)
        if current != match.replacements[idx]:
            n += 1
    return n


def _unique_append(items: list[GrammarSuggestion], item: GrammarSuggestion) -> None:
    if any(existing.id == item.id for existing in items):
        return
    items.append(item)


def _suggestion_from_matches(
    text: str,
    matches: list[GrammarMatch],
    replacement_index: int,
    sid: str,
    label: str,
) -> GrammarSuggestion:
    actionable = [m for m in matches if m.replacements]
    revised = apply_matches(text, actionable, replacement_index)
    orig_parts, rev_parts, changes = build_match_parts(text, actionable, replacement_index)
    return GrammarSuggestion(
        id=sid,
        label=label,
        text=revised,
        change_count=_effective_changes(text, actionable, replacement_index),
        original_parts=orig_parts,
        revised_parts=rev_parts,
        changes=changes,
    )


def suggestions_from_matches(
    text: str,
    matches: list[GrammarMatch],
) -> list[GrammarSuggestion]:
    actionable = punctuation_matches(text, matches)
    out: list[GrammarSuggestion] = []
    if actionable:
        fixed = _suggestion_from_matches(text, actionable, 0, "fixed", "Исправления")
        _unique_append(out, fixed)
        alt = _suggestion_from_matches(text, actionable, 1, "alt", "Другой вариант")
        if alt.text != fixed.text:
            _unique_append(out, alt)

    if not out:
        orig_parts, rev_parts, changes = build_diff_parts(text, text)
        return [
            GrammarSuggestion(
                id="same",
                label="Без изменений",
                text=text,
                change_count=0,
                original_parts=orig_parts,
                revised_parts=rev_parts,
                changes=changes,
            )
        ]
    return out


def matches_from_languagetool(payload: dict, source_text: str = "") -> list[GrammarMatch]:
    raw_matches = payload.get("matches") or []
    out: list[GrammarMatch] = []
    for item in raw_matches[:_MAX_ISSUES]:
        if not isinstance(item, dict):
            continue
        try:
            offset = int(item.get("offset", 0))
            length = int(item.get("length", 0))
        except (TypeError, ValueError):
            continue
        if length <= 0:
            continue
        replacements: list[str] = []
        for repl in item.get("replacements") or []:
            if isinstance(repl, dict):
                value = repl.get("value")
            else:
                value = repl
            if isinstance(value, str) and value and value not in replacements:
                replacements.append(value)
            if len(replacements) >= _MAX_REPLACEMENTS:
                break
        rule = item.get("rule") if isinstance(item.get("rule"), dict) else {}
        issue_type = str(rule.get("issueType") or "")
        if issue_type.strip().lower() in _STYLE_ISSUE_TYPES:
            continue
        out.append(
            GrammarMatch(
                offset=offset,
                length=length,
                message=str(item.get("message") or "").strip(),
                short_message=str(item.get("shortMessage") or "").strip(),
                replacements=replacements,
                issue_type=issue_type,
            )
        )
    return out


def merge_matches(groups: list[list[GrammarMatch]]) -> list[GrammarMatch]:
    combined: list[GrammarMatch] = []
    for group in groups:
        combined.extend(group)
    combined.sort(key=lambda m: (m.offset, -m.length))
    kept: list[GrammarMatch] = []
    for match in combined:
        overlaps = any(
            not (match.offset + match.length <= other.offset or match.offset >= other.offset + other.length)
            for other in kept
        )
        if overlaps:
            continue
        kept.append(match)
    return kept


def detected_language(payloads: list[dict], fallback: str) -> str:
    for payload in payloads:
        lang = payload.get("language")
        if isinstance(lang, dict):
            detected = lang.get("detectedLanguage")
            if isinstance(detected, dict) and detected.get("language"):
                return str(detected["language"])
            if lang.get("code"):
                return str(lang["code"])
    return fallback


def response_from_matches(
    text: str,
    matches: list[GrammarMatch],
    language: str = "",
) -> GrammarCheckResponse:
    issues = [
        GrammarIssue(
            offset=m.offset,
            length=m.length,
            message=m.message,
            short_message=m.short_message,
            replacements=m.replacements[:_MAX_REPLACEMENTS],
            issue_type=m.issue_type,
        )
        for m in matches
    ]
    return GrammarCheckResponse(
        original=text,
        suggestions=suggestions_from_matches(text, matches),
        issues=issues,
        advice=advice_from_matches(text, matches),
        language=language,
    )


def _configured_languages(text: str) -> list[str]:
    configured = (settings.languagetool_language or "auto").strip() or "auto"
    if configured.lower() == "auto":
        return languages_for_text(text)
    return [configured]


async def post_languagetool(text: str, language: str | None = None) -> dict:
    url = (settings.languagetool_api_url or "").strip()
    if not url:
        raise GrammarServiceError("Сервис проверки не настроен.")
    lang = (language or settings.languagetool_language or "auto").strip() or "auto"
    data = {
        "text": text,
        "language": lang,
        "enabledOnly": "false",
        "disabledCategories": "STYLE,REDUNDANCY,COLLOQUIALISMS,WIKIPEDIA",
    }
    if lang.lower() == "auto":
        data["preferredVariants"] = "ru-RU,en-US"
    async with httpx.AsyncClient(timeout=_TIMEOUT_SEC) as client:
        response = await client.post(
            url,
            data=data,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "application/json",
            },
        )
        if response.status_code == 429:
            raise GrammarServiceError(
                "Сервис проверки сейчас занят. Подождите минуту и попробуйте снова."
            )
        if response.status_code >= 400:
            raise GrammarServiceError("Сервис проверки временно недоступен.")
        payload = response.json()
        if not isinstance(payload, dict):
            raise GrammarServiceError("Сервис проверки вернул непонятный ответ.")
        return payload


class GrammarServiceError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class GrammarRequestError(GrammarServiceError):
    """Некорректный фрагмент — это ошибка клиента, не сбой LanguageTool."""


async def check_text(text: str) -> GrammarCheckResponse:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    if not cleaned.strip():
        raise GrammarRequestError("Выделите текст для проверки.")
    if len(cleaned) > GRAMMAR_MAX_CHARS:
        raise GrammarRequestError(f"Слишком длинный фрагмент. Максимум {GRAMMAR_MAX_CHARS} знаков.")
    langs = _configured_languages(cleaned)
    check_src, inserts = text_for_languagetool(cleaned)
    payloads: list[dict] = []
    try:
        for lang in langs:
            payloads.append(await post_languagetool(check_src, lang))
    except httpx.TimeoutException as exc:
        raise GrammarServiceError("Проверка заняла слишком много времени.") from exc
    except httpx.HTTPError as exc:
        raise GrammarServiceError("Не удалось связаться с сервисом проверки.") from exc
    remapped: list[GrammarMatch] = []
    for payload in payloads:
        for match in matches_from_languagetool(payload, check_src):
            mapped = remap_match(match, inserts)
            if mapped is None or is_cross_line_repeat(cleaned, mapped):
                continue
            remapped.append(mapped)
    matches = merge_matches(
        [remapped, drop_duplicate_sentence_ends(remapped, line_end_matches(cleaned))]
    )
    language = detected_language(payloads, langs[0] if langs else "")
    return response_from_matches(cleaned, matches, language=language)
