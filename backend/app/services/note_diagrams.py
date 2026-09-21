"""Извлечение и правка блоков draw.io (diagrams.net) внутри TipTap JSON заметки."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import or_, select
from sqlalchemy.sql import Select

from app.models.note import Note
from app.models.share import NoteShare
from app.services.note_schemas import block_id_from_node, title_from_node

C4_BLOCK_TYPE = "c4Block"
_DIAGRAM_NAME_RE = re.compile(r'<diagram[^>]+name="([^"]{1,80})"', re.IGNORECASE)
_MXCELL_SHAPE_RE = re.compile(r'<mxCell[^>]+(?:vertex="1"|edge="1")', re.IGNORECASE)


def walk_c4_nodes(doc: dict) -> list[dict]:
    found: list[dict] = []

    def walk(node: object) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == C4_BLOCK_TYPE:
            found.append(node)
        for child in node.get("content") or []:
            walk(child)

    walk(doc)
    return found


def source_from_node(node: dict) -> str:
    attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
    scene = attrs.get("scene")
    if isinstance(scene, str) and scene.strip():
        return scene
    return ""


def diagram_caption(source: str, index: int, node: dict | None = None) -> str:
    titled = title_from_node(node) if node else None
    if titled:
        return titled
    name_match = _DIAGRAM_NAME_RE.search(source or "")
    if name_match:
        return name_match.group(1).strip()
    return f"Диаграмма {index + 1}"


def diagram_element_count(source: str) -> int:
    return len(_MXCELL_SHAPE_RE.findall(source or ""))


def replace_c4_attrs(
    doc: dict,
    index: int,
    *,
    scene: str | None = None,
    title: str | None = None,
    block_id: str | None = None,
) -> dict:
    nodes = walk_c4_nodes(doc)
    if not nodes:
        raise KeyError("no diagrams")
    target = None
    if block_id:
        for node in nodes:
            if block_id_from_node(node) == block_id:
                target = node
                break
    if target is None:
        if index < 0 or index >= len(nodes):
            raise IndexError("diagram index")
        target = nodes[index]
    attrs = target.get("attrs")
    if not isinstance(attrs, dict):
        attrs = {}
        target["attrs"] = attrs
    if scene is not None:
        attrs["scene"] = scene
    if title is not None:
        attrs["title"] = title.strip()[:80] or "Диаграмма"
    if block_id and not attrs.get("blockId"):
        attrs["blockId"] = block_id
    return doc


def notes_with_diagram_candidates(user_id: uuid.UUID) -> Select[tuple[Note]]:
    """Доступные пользователю незакрытые заметки, где может быть draw.io-диаграмма."""
    shared_ids = select(NoteShare.note_id).where(NoteShare.shared_with_user_id == user_id)
    return (
        select(Note)
        .where(Note.deleted_at.is_(None))
        .where((Note.owner_id == user_id) | (Note.id.in_(shared_ids)))
        .where(
            or_(
                Note.content_plain.contains("[диаграмма"),
                Note.content_json.contains("c4Block"),
                Note.content_json.contains("<mxfile"),
            )
        )
        .order_by(Note.updated_at.desc())
    )
