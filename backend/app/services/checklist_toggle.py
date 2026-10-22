"""Отметка чек-бокса по ссылке «чек-лист».

По такой ссылке документ целиком не принимается: клиент присылает только номер
пункта и нужное состояние, а сервер сам меняет `attrs.checked` у этого taskItem.
Всё остальное в заметке остаётся байт-в-байт как было.
"""

import json
from collections.abc import Iterator
from typing import Any


class ChecklistConflict(Exception):
    """Пункт с таким номером не найден или его текст изменился — список устарел."""


def iter_task_items(doc: Any) -> Iterator[dict[str, Any]]:
    """taskItem в порядке обхода документа (тот же pre-order, что у ProseMirror descendants)."""
    if not isinstance(doc, dict):
        return
    if doc.get("type") == "taskItem":
        yield doc
    content = doc.get("content")
    if isinstance(content, list):
        for child in content:
            yield from iter_task_items(child)


def task_item_text(node: dict[str, Any]) -> str:
    """Текст пункта без разметки — так же его считает клиент (ProseMirror textContent)."""
    parts: list[str] = []

    def walk(n: Any) -> None:
        if not isinstance(n, dict):
            return
        if n.get("type") == "text" and isinstance(n.get("text"), str):
            parts.append(n["text"])
        content = n.get("content")
        if isinstance(content, list):
            for child in content:
                walk(child)

    walk(node)
    return "".join(parts)


def apply_checklist_toggle(content_json: str, index: int, checked: bool, expected_text: str) -> str | None:
    """Новый content_json с отмеченным пунктом; None, если пункт уже в нужном состоянии.

    expected_text защищает от гонки: владелец мог переставить или удалить пункты,
    пока чек-лист был открыт, — тогда номер указывает уже на другой пункт.
    """
    try:
        doc = json.loads(content_json)
    except (json.JSONDecodeError, TypeError) as e:
        raise ChecklistConflict("Заметка повреждена") from e
    for i, item in enumerate(iter_task_items(doc)):
        if i != index:
            continue
        if task_item_text(item) != expected_text:
            raise ChecklistConflict("Список изменился — обновите страницу")
        attrs = item.get("attrs")
        if not isinstance(attrs, dict):
            attrs = {}
            item["attrs"] = attrs
        if bool(attrs.get("checked")) == checked:
            return None
        attrs["checked"] = checked
        return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    raise ChecklistConflict("Пункт не найден — обновите страницу")
