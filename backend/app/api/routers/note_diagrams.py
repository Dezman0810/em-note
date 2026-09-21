import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, require_schemas_access
from app.models.note import Note
from app.models.tag import Tag
from app.models.user import User
from app.schemas.note_diagram import NoteDiagramDetail, NoteDiagramListItem, NoteDiagramPatch
from app.services.note_access import Access, ensure_note_editable, get_note_access
from app.services.note_diagrams import (
    diagram_caption,
    diagram_element_count,
    notes_with_diagram_candidates,
    replace_c4_attrs,
    source_from_node,
    walk_c4_nodes,
)
from app.services.note_personal_view import personal_tag_ids_map
from app.services.note_schemas import (
    access_map_for_notes,
    block_id_from_node,
    dump_tiptap,
    parse_tiptap,
)
from app.utils.text import plain_text_from_tiptap_json

router = APIRouter(prefix="/diagrams", tags=["diagrams"])


async def _visible_tag_names(db: AsyncSession, user: User, note: Note) -> list[str]:
    if note.owner_id == user.id:
        return [t.name for t in note.tags]
    personal = await personal_tag_ids_map(db, user.id, [note.id])
    ids = personal.get(note.id, [])
    if not ids:
        return []
    rows = (await db.execute(select(Tag.name).where(Tag.id.in_(ids), Tag.user_id == user.id))).all()
    return [name for (name,) in rows]


def _item_from_node(
    *,
    note_id: uuid.UUID,
    note_title: str,
    schema_index: int,
    node: dict,
    access: Access,
    updated_at: datetime,
    tag_names: list[str] | None = None,
    scene: str | None = None,
) -> NoteDiagramListItem | NoteDiagramDetail:
    raw_scene = scene if scene is not None else source_from_node(node)
    payload = {
        "note_id": note_id,
        "note_title": note_title,
        "schema_index": schema_index,
        "block_id": block_id_from_node(node),
        "caption": diagram_caption(raw_scene, schema_index, node),
        "element_count": diagram_element_count(raw_scene),
        "can_edit": access in (Access.owner, Access.edit),
        "my_access": access.value,
        "updated_at": updated_at,
        "tag_names": tag_names or [],
    }
    if scene is not None:
        return NoteDiagramDetail(**payload, scene=raw_scene)
    return NoteDiagramListItem(**payload)


@router.get("", response_model=list[NoteDiagramListItem])
async def list_diagrams(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_schemas_access)],
) -> list[NoteDiagramListItem]:
    result = await db.execute(
        notes_with_diagram_candidates(user.id).options(selectinload(Note.tags))
    )
    notes = list(result.scalars().unique().all())
    acc_map = await access_map_for_notes(db, user.id, notes)
    shared_ids = [n.id for n in notes if n.owner_id != user.id]
    personal = await personal_tag_ids_map(db, user.id, shared_ids)
    user_tags = list(
        (await db.execute(select(Tag).where(Tag.user_id == user.id))).scalars().all()
    )
    tag_name_by_id = {t.id: t.name for t in user_tags}

    def tag_names_for(note: Note) -> list[str]:
        if note.owner_id == user.id:
            return [t.name for t in note.tags]
        return [tag_name_by_id[tid] for tid in personal.get(note.id, []) if tid in tag_name_by_id]

    items: list[NoteDiagramListItem] = []
    for note in notes:
        doc = parse_tiptap(note.content_json)
        if doc is None:
            continue
        access = acc_map.get(note.id, Access.read)
        names = tag_names_for(note)
        for index, node in enumerate(walk_c4_nodes(doc)):
            items.append(
                _item_from_node(
                    note_id=note.id,
                    note_title=note.title,
                    schema_index=index,
                    node=node,
                    access=access,
                    updated_at=note.updated_at,
                    tag_names=names,
                )
            )
    return items


@router.get("/{note_id}/{schema_index}", response_model=NoteDiagramDetail)
async def get_diagram(
    note_id: uuid.UUID,
    schema_index: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_schemas_access)],
) -> NoteDiagramDetail:
    if schema_index < 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Диаграмма не найдена")
    note, access = await get_note_access(db, note_id, user.id)
    doc = parse_tiptap(note.content_json)
    nodes = walk_c4_nodes(doc) if doc else []
    if schema_index >= len(nodes):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Диаграмма не найдена")
    node = nodes[schema_index]
    return _item_from_node(
        note_id=note.id,
        note_title=note.title,
        schema_index=schema_index,
        node=node,
        access=access,
        updated_at=note.updated_at,
        tag_names=await _visible_tag_names(db, user, note),
        scene=source_from_node(node),
    )


@router.patch("/{note_id}/{schema_index}", response_model=NoteDiagramDetail)
async def patch_diagram(
    note_id: uuid.UUID,
    schema_index: int,
    body: NoteDiagramPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_schemas_access)],
) -> NoteDiagramDetail:
    if schema_index < 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Диаграмма не найдена")
    note, access = await get_note_access(db, note_id, user.id)
    ensure_note_editable(note, access)
    doc = parse_tiptap(note.content_json)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный документ заметки")
    if body.scene is None and body.title is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нечего обновлять")
    try:
        replace_c4_attrs(
            doc,
            schema_index,
            scene=body.scene,
            title=body.title,
            block_id=body.block_id,
        )
    except (KeyError, IndexError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Диаграмма не найдена")
    note.content_json = dump_tiptap(doc)
    note.content_plain = plain_text_from_tiptap_json(note.content_json)
    note.updated_at = datetime.now(timezone.utc)
    await db.flush()
    nodes = walk_c4_nodes(doc)
    node = nodes[schema_index] if schema_index < len(nodes) else nodes[0]
    if body.block_id:
        for i, candidate in enumerate(nodes):
            if block_id_from_node(candidate) == body.block_id:
                schema_index = i
                node = candidate
                break
    return _item_from_node(
        note_id=note.id,
        note_title=note.title,
        schema_index=schema_index,
        node=node,
        access=access,
        updated_at=note.updated_at,
        tag_names=await _visible_tag_names(db, user, note),
        scene=source_from_node(node),
    )
