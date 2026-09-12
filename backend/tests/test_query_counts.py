"""Число SQL-запросов не должно расти с числом заметок/шеров (защита от N+1).

Считаем инструкции через событие before_cursor_execute на sync-Engine: async-движок
проходит через ту же машинерию, поэтому ловятся все запросы.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.engine import Engine


@contextmanager
def count_queries() -> Iterator[list[str]]:
    seen: list[str] = []

    def on_execute(
        _conn: Any, _cursor: Any, statement: str, *_args: Any, **_kwargs: Any
    ) -> None:
        seen.append(statement)

    event.listen(Engine, "before_cursor_execute", on_execute)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", on_execute)


async def _register_and_login(client: AsyncClient, email: str) -> tuple[dict[str, str], str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password99", "display_name": "Q"},
    )
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]
    r = await client.post("/api/auth/login", json={"email": email, "password": "password99"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, user_id


async def _share_n_notes(
    client: AsyncClient, owner: dict[str, str], recipient_id: str, count: int
) -> list[str]:
    ids: list[str] = []
    for i in range(count):
        n = await client.post(
            "/api/notes", json={"title": f"shared {i}", "content_json": "{}"}, headers=owner
        )
        assert n.status_code == 201, n.text
        note_id = n.json()["id"]
        sh = await client.post(
            f"/api/notes/{note_id}/shares",
            headers=owner,
            json={"shared_with_user_id": recipient_id, "role": "viewer"},
        )
        assert sh.status_code == 201, sh.text
        ids.append(note_id)
    return ids


async def test_auth_me_query_count_does_not_grow_with_shares(client: AsyncClient) -> None:
    h_owner, _ = await _register_and_login(client, "tagtest@example.com")
    h_few, few_id = await _register_and_login(client, "qfew@example.com")
    h_many, many_id = await _register_and_login(client, "qmany@example.com")

    await _share_n_notes(client, h_owner, few_id, 2)
    await _share_n_notes(client, h_owner, many_id, 12)

    # Первый /me довешивает личные метки «Доступ по email», дальше делать нечего.
    assert (await client.get("/api/auth/me", headers=h_few)).status_code == 200
    assert (await client.get("/api/auth/me", headers=h_many)).status_code == 200

    with count_queries() as few_queries:
        r = await client.get("/api/auth/me", headers=h_few)
        assert r.status_code == 200, r.text
    with count_queries() as many_queries:
        r = await client.get("/api/auth/me", headers=h_many)
        assert r.status_code == 200, r.text

    assert len(few_queries) == len(many_queries), (few_queries, many_queries)
    assert len(few_queries) <= 4, few_queries


async def test_notes_list_query_count_does_not_grow_with_notes(client: AsyncClient) -> None:
    h_owner, _ = await _register_and_login(client, "tagtest@example.com")
    h_few, few_id = await _register_and_login(client, "qlistfew@example.com")
    h_many, many_id = await _register_and_login(client, "qlistmany@example.com")

    await _share_n_notes(client, h_owner, few_id, 2)
    await _share_n_notes(client, h_owner, many_id, 12)
    assert (await client.get("/api/auth/me", headers=h_few)).status_code == 200
    assert (await client.get("/api/auth/me", headers=h_many)).status_code == 200

    with count_queries() as few_queries:
        r = await client.get("/api/notes", headers=h_few)
        assert r.status_code == 200, r.text
        assert len(r.json()) == 2
    with count_queries() as many_queries:
        r = await client.get("/api/notes", headers=h_many)
        assert r.status_code == 200, r.text
        assert len(r.json()) == 12

    assert len(few_queries) == len(many_queries), (few_queries, many_queries)


async def test_tag_counts_query_count_does_not_grow_with_tags(client: AsyncClient) -> None:
    h, _ = await _register_and_login(client, "qtags@example.com")
    parent = await client.post("/api/tags", json={"name": "P"}, headers=h)
    assert parent.status_code == 201, parent.text

    with count_queries() as few_queries:
        assert (await client.get("/api/tags/counts", headers=h)).status_code == 200

    for i in range(10):
        r = await client.post(
            "/api/tags", json={"name": f"T{i}", "parent_id": parent.json()["id"]}, headers=h
        )
        assert r.status_code == 201, r.text

    with count_queries() as many_queries:
        assert (await client.get("/api/tags/counts", headers=h)).status_code == 200

    assert len(few_queries) == len(many_queries), (few_queries, many_queries)


async def test_folder_note_counts_query_count_does_not_grow_with_folders(
    client: AsyncClient,
) -> None:
    h, _ = await _register_and_login(client, "qfolders@example.com")
    with count_queries() as few_queries:
        assert (await client.get("/api/folders/note-counts", headers=h)).status_code == 200

    for i in range(10):
        r = await client.post("/api/folders", json={"name": f"F{i}"}, headers=h)
        assert r.status_code == 201, r.text

    with count_queries() as many_queries:
        assert (await client.get("/api/folders/note-counts", headers=h)).status_code == 200

    assert len(few_queries) == len(many_queries), (few_queries, many_queries)


# «FROM notes» без алиаса: сама строка заметки, а не подзапрос selectinload,
# который джойнит notes AS notes_1 ради меток.
_NOTE_ROW_SELECT = re.compile(r"FROM notes(?!\s+AS)")


def _note_selects(statements: list[str]) -> list[str]:
    return [
        s
        for s in statements
        if s.lstrip().upper().startswith("SELECT") and _NOTE_ROW_SELECT.search(s)
    ]


async def test_note_is_loaded_once_per_request(client: AsyncClient) -> None:
    """get_note и attach/detach метки читали заметку по 2–4 раза за запрос."""
    h, _ = await _register_and_login(client, "qnote@example.com")
    n = await client.post(
        "/api/notes", json={"title": "One", "content_json": "{}"}, headers=h
    )
    assert n.status_code == 201, n.text
    note_id = n.json()["id"]
    tag = await client.post("/api/tags", json={"name": "Mark"}, headers=h)
    assert tag.status_code == 201, tag.text
    tag_id = tag.json()["id"]

    with count_queries() as get_queries:
        r = await client.get(f"/api/notes/{note_id}", headers=h)
        assert r.status_code == 200, r.text
    assert len(_note_selects(get_queries)) == 1, get_queries
    assert len(get_queries) <= 3, get_queries

    with count_queries() as attach_queries:
        r = await client.post(f"/api/notes/{note_id}/tags/{tag_id}", headers=h)
        assert r.status_code == 200, r.text
    assert len(_note_selects(attach_queries)) == 1, attach_queries

    with count_queries() as patch_queries:
        r = await client.patch(f"/api/notes/{note_id}", json={"title": "Two"}, headers=h)
        assert r.status_code == 200, r.text
    assert len(_note_selects(patch_queries)) == 1, patch_queries

    with count_queries() as detach_queries:
        r = await client.delete(f"/api/notes/{note_id}/tags/{tag_id}", headers=h)
        assert r.status_code == 200, r.text
    assert len(_note_selects(detach_queries)) == 1, detach_queries
