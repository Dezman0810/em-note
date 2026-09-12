"""Построение запроса списка/поиска заметок: доступ, папки, метки.

Метки пользователя и папки читаются по одному разу на запрос, а не в цикле по
каждому идентификатору из query-параметров.
"""

import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, selectinload

from app.models.note import Note
from app.models.share import NoteShare
from app.models.tag import Tag
from app.services.folder_access import assert_folders_owned
from app.services.note_personal_view import (
    folder_exclude_predicate,
    folder_scope_predicate,
    tag_match_predicate,
)
from app.services.tag_subtree import subtree_tag_ids

# Компактное представление (NoteRead.from_note_for_list) не отдаёт content_json,
# поэтому тяжёлую колонку не тащим из БД; raiseload ловит случайную дозагрузку.
LIST_LOAD_OPTIONS = (selectinload(Note.tags), defer(Note.content_json, raiseload=True))


@dataclass(slots=True)
class NoteListFilters:
    folder_ids: list[uuid.UUID] = field(default_factory=list)
    unfoldered: bool = False
    tag_roots: list[uuid.UUID] = field(default_factory=list)
    conjunct_roots: list[uuid.UUID] = field(default_factory=list)
    exclude_roots: list[uuid.UUID] = field(default_factory=list)
    exclude_undo_roots: list[uuid.UUID] = field(default_factory=list)
    exclude_folder_ids: list[uuid.UUID] = field(default_factory=list)
    tag_match_all: bool = False

    @property
    def uses_tags(self) -> bool:
        return bool(
            self.tag_roots or self.conjunct_roots or self.exclude_roots or self.exclude_undo_roots
        )


class TagTrees:
    """Метки пользователя, загруженные один раз; поддеревья считаются в памяти."""

    def __init__(self, tags: list[Tag]) -> None:
        self._tags = tags
        self._known = {t.id for t in tags}
        self._cache: dict[uuid.UUID, list[uuid.UUID]] = {}

    def subtree(self, tag_id: uuid.UUID) -> list[uuid.UUID]:
        """Поддерево метки; чужая или несуществующая метка — 404, как при db.get(Tag)."""
        if tag_id not in self._known:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
        cached = self._cache.get(tag_id)
        if cached is None:
            cached = subtree_tag_ids(tag_id, self._tags)
            self._cache[tag_id] = cached
        return cached

    def union_subtrees(self, tag_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        out: set[uuid.UUID] = set()
        for tid in tag_ids:
            out.update(self.subtree(tid))
        return out


async def load_tag_trees(db: AsyncSession, user_id: uuid.UUID) -> TagTrees:
    rows = await db.execute(select(Tag).where(Tag.user_id == user_id))
    return TagTrees(list(rows.scalars().all()))


def accessible_notes_query(user_id: uuid.UUID) -> Select[tuple[Note]]:
    shared_ids = select(NoteShare.note_id).where(NoteShare.shared_with_user_id == user_id)
    return (
        select(Note)
        .where(Note.deleted_at.is_(None))
        .where((Note.owner_id == user_id) | (Note.id.in_(shared_ids)))
        .order_by(Note.updated_at.desc())
        .options(*LIST_LOAD_OPTIONS)
    )


def _apply_positive_tag_filter(
    q: Select[tuple[Note]],
    user_id: uuid.UUID,
    trees: TagTrees,
    tag_roots: list[uuid.UUID],
    tag_match_all: bool,
) -> Select[tuple[Note]]:
    """Положительный фильтр по меткам: объединение поддеревьев (ИЛИ) или все корни (И)."""
    if tag_match_all and len(tag_roots) > 1:
        for tid in tag_roots:
            subtree = trees.subtree(tid)
            if subtree:
                q = q.where(tag_match_predicate(user_id, subtree))
        return q
    return q.where(tag_match_predicate(user_id, list(trees.union_subtrees(tag_roots))))


def _effective_exclude_tag_ids(
    trees: TagTrees, exclude_roots: list[uuid.UUID], undo_roots: list[uuid.UUID]
) -> list[uuid.UUID]:
    """Поддеревья exclude_tag_id минус поддеревья exclude_tag_undo_id (вырезание из исключения)."""
    if not exclude_roots:
        return []
    excluded = trees.union_subtrees(exclude_roots)
    if not undo_roots:
        return list(excluded)
    return list(excluded - trees.union_subtrees(undo_roots))


async def build_note_list_query(
    db: AsyncSession,
    user_id: uuid.UUID,
    filters: NoteListFilters,
    *,
    text_predicate: ColumnElement[bool] | None = None,
) -> Select[tuple[Note]]:
    """Один запрос-селект со всеми фильтрами; папки/метки валидируются заранее."""
    q = accessible_notes_query(user_id)
    if text_predicate is not None:
        q = q.where(text_predicate)

    if filters.folder_ids:
        await assert_folders_owned(db, filters.folder_ids, user_id)
    if filters.unfoldered or filters.folder_ids:
        q = q.where(
            folder_scope_predicate(
                user_id, None if filters.unfoldered else filters.folder_ids, filters.unfoldered
            )
        )

    if filters.uses_tags:
        trees = await load_tag_trees(db, user_id)
        if filters.tag_roots:
            q = _apply_positive_tag_filter(
                q, user_id, trees, filters.tag_roots, filters.tag_match_all
            )
        for cid in filters.conjunct_roots:
            subtree = trees.subtree(cid)
            if subtree:
                q = q.where(tag_match_predicate(user_id, subtree))
        excluded = _effective_exclude_tag_ids(
            trees, filters.exclude_roots, filters.exclude_undo_roots
        )
        if excluded:
            q = q.where(~tag_match_predicate(user_id, excluded))

    if filters.exclude_folder_ids:
        await assert_folders_owned(db, filters.exclude_folder_ids, user_id)
        q = q.where(~folder_exclude_predicate(user_id, filters.exclude_folder_ids))
    return q
