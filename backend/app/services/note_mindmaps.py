"""Извлечение и правка блоков интеллект-карт внутри TipTap JSON заметки."""

from __future__ import annotations

import json
import re
import uuid

from sqlalchemy import or_, select
from sqlalchemy.sql import Select

from app.models.note import Note
from app.models.share import NoteShare
from app.services.note_schemas import block_id_from_node, title_from_node

MINDMAP_TYPE = "mindmapBlock"
_HTML_RE = re.compile(r"<[^>]+>")
_PLACEHOLDER_ROOT = frozenset(
    {"главная", "центр", "root", "central topic", "根节点", "中心主题"}
)


def walk_mindmap_nodes(doc: dict) -> list[dict]:
    found: list[dict] = []

    def walk(node: object) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == MINDMAP_TYPE:
            found.append(node)
        for child in node.get("content") or []:
            walk(child)

    walk(doc)
    return found


def _root_text(scene: str) -> str:
    try:
        data = json.loads(scene)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    root = data.get("root")
    if isinstance(root, dict) and isinstance(root.get("root"), dict):
        root = root["root"]
    if not isinstance(root, dict):
        return ""
    payload = root.get("data")
    if not isinstance(payload, dict):
        return ""
    raw = payload.get("text")
    if not isinstance(raw, str):
        return ""
    text = _HTML_RE.sub(" ", raw).replace("&nbsp;", " ")
    return " ".join(text.split())[:80]


def mindmap_caption(scene: str, index: int, node: dict | None = None) -> str:
    titled = title_from_node(node) if node else None
    if titled:
        return titled
    text = _root_text(scene)
    if text and text.casefold() not in _PLACEHOLDER_ROOT:
        return text
    return f"Карта {index + 1}"


def mindmap_node_count(scene: str) -> int:
    try:
        data = json.loads(scene)
    except (json.JSONDecodeError, TypeError):
        return 0
    if not isinstance(data, dict):
        return 0

    def count(node: object) -> int:
        if not isinstance(node, dict):
            return 0
        n = 1 if isinstance(node.get("data"), dict) else 0
        for child in node.get("children") or []:
            n += count(child)
        inner = node.get("root")
        if isinstance(inner, dict):
            n += count(inner)
        return n

    return count(data.get("root"))


def replace_mindmap_attrs(
    doc: dict,
    index: int,
    *,
    scene: str | None = None,
    title: str | None = None,
    block_id: str | None = None,
) -> dict:
    nodes = walk_mindmap_nodes(doc)
    if not nodes:
        raise KeyError("no mindmaps")
    target = None
    if block_id:
        for node in nodes:
            if block_id_from_node(node) == block_id:
                target = node
                break
    if target is None:
        if index < 0 or index >= len(nodes):
            raise IndexError("mindmap index")
        target = nodes[index]
    attrs = target.get("attrs")
    if not isinstance(attrs, dict):
        attrs = {}
        target["attrs"] = attrs
    if scene is not None:
        attrs["scene"] = scene
    if title is not None:
        attrs["title"] = title.strip()[:80] or "Карта"
    if block_id and not attrs.get("blockId"):
        attrs["blockId"] = block_id
    return doc


def notes_with_mindmap_candidates(user_id: uuid.UUID) -> Select[tuple[Note]]:
    """Доступные пользователю незакрытые заметки, где может быть карта."""
    shared_ids = select(NoteShare.note_id).where(NoteShare.shared_with_user_id == user_id)
    return (
        select(Note)
        .where(Note.deleted_at.is_(None))
        .where((Note.owner_id == user_id) | (Note.id.in_(shared_ids)))
        .where(
            or_(
                Note.content_plain.contains("[карта]"),
                Note.content_json.contains("mindmapBlock"),
            )
        )
        .order_by(Note.updated_at.desc())
    )
