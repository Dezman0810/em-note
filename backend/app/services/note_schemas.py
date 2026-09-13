"""Извлечение и правка блоков Excalidraw (схем) внутри TipTap JSON заметки."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.note import Note
from app.models.share import NoteShare, ShareRole
from app.services.note_access import Access

EXCALIDRAW_TYPE = "excalidrawBlock"


def parse_tiptap(content_json: str) -> dict | None:
    try:
        doc = json.loads(content_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    return doc if isinstance(doc, dict) else None


def walk_excalidraw_nodes(doc: dict) -> list[dict]:
    found: list[dict] = []

    def walk(node: object) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == EXCALIDRAW_TYPE:
            found.append(node)
        for child in node.get("content") or []:
            walk(child)

    walk(doc)
    return found


def dump_tiptap(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False)


def scene_from_node(node: dict) -> str:
    attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
    scene = attrs.get("scene")
    if isinstance(scene, str):
        return scene
    if isinstance(scene, dict):
        return json.dumps(scene, ensure_ascii=False)
    return "{}"


def block_id_from_node(node: dict) -> str | None:
    attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
    raw = attrs.get("blockId")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def title_from_node(node: dict) -> str | None:
    attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
    raw = attrs.get("title")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()[:80]
    return None


def schema_caption(scene: str, index: int, node: dict | None = None) -> str:
    titled = title_from_node(node) if node else None
    if titled:
        return titled
    try:
        data = json.loads(scene)
    except (json.JSONDecodeError, TypeError):
        return f"Схема {index + 1}"
    if not isinstance(data, dict):
        return f"Схема {index + 1}"
    for el in data.get("elements") or []:
        if not isinstance(el, dict) or el.get("isDeleted"):
            continue
        if el.get("type") == "text":
            text = str(el.get("text") or "").strip()
            if text:
                return text[:80]
    return f"Схема {index + 1}"


def schema_element_count(scene: str) -> int:
    try:
        data = json.loads(scene)
    except (json.JSONDecodeError, TypeError):
        return 0
    if not isinstance(data, dict):
        return 0
    n = 0
    for el in data.get("elements") or []:
        if isinstance(el, dict) and not el.get("isDeleted"):
            n += 1
    return n


def replace_schema_attrs(
    doc: dict,
    index: int,
    *,
    scene: str | None = None,
    title: str | None = None,
    block_id: str | None = None,
) -> dict:
    nodes = walk_excalidraw_nodes(doc)
    if not nodes:
        raise KeyError("no schemas")
    target = None
    if block_id:
        for node in nodes:
            if block_id_from_node(node) == block_id:
                target = node
                break
    if target is None:
        if index < 0 or index >= len(nodes):
            raise IndexError("schema index")
        target = nodes[index]
    attrs = target.get("attrs")
    if not isinstance(attrs, dict):
        attrs = {}
        target["attrs"] = attrs
    if scene is not None:
        attrs["scene"] = scene
    if title is not None:
        attrs["title"] = title.strip()[:80] or "Схема"
    if block_id and not attrs.get("blockId"):
        attrs["blockId"] = block_id
    return doc


def replace_schema_scene(
    doc: dict,
    index: int,
    scene: str,
    block_id: str | None = None,
) -> dict:
    return replace_schema_attrs(doc, index, scene=scene, block_id=block_id)


def notes_with_schema_candidates(user_id: uuid.UUID) -> Select[tuple[Note]]:
    """Доступные пользователю незакрытые заметки, где может быть схема."""
    shared_ids = select(NoteShare.note_id).where(NoteShare.shared_with_user_id == user_id)
    return (
        select(Note)
        .where(Note.deleted_at.is_(None))
        .where((Note.owner_id == user_id) | (Note.id.in_(shared_ids)))
        .where(
            or_(
                Note.content_plain.contains("[схема]"),
                Note.content_json.contains("excalidrawBlock"),
            )
        )
        .order_by(Note.updated_at.desc())
    )


async def access_map_for_notes(
    db: AsyncSession, user_id: uuid.UUID, notes: list[Note]
) -> dict[uuid.UUID, Access]:
    out: dict[uuid.UUID, Access] = {}
    shared_ids: list[uuid.UUID] = []
    for n in notes:
        if n.owner_id == user_id:
            out[n.id] = Access.owner
        else:
            shared_ids.append(n.id)
    if not shared_ids:
        return out
    rows = (
        await db.execute(
            select(NoteShare.note_id, NoteShare.role).where(
                NoteShare.shared_with_user_id == user_id,
                NoteShare.note_id.in_(shared_ids),
            )
        )
    ).all()
    role_by_note = {nid: role for nid, role in rows}
    for nid in shared_ids:
        role = role_by_note.get(nid)
        out[nid] = Access.edit if role == ShareRole.editor.value else Access.read
    return out
