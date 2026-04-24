"""Проверка счётчиков меток и фильтрации списка заметок по tag_id (включая поддерево)."""

from httpx import AsyncClient


async def _auth_headers(
    client: AsyncClient, email: str = "tagtest@example.com", password: str = "password99"
) -> dict[str, str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "Tag Test"},
    )
    assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_tag_counts_and_list_filter_subtree(client: AsyncClient) -> None:
    h = await _auth_headers(client)

    parent = await client.post("/api/tags", json={"name": "Parent"}, headers=h)
    assert parent.status_code == 201, parent.text
    parent_id = parent.json()["id"]

    child = await client.post(
        "/api/tags",
        json={"name": "Child", "parent_id": parent_id},
        headers=h,
    )
    assert child.status_code == 201, child.text
    child_id = child.json()["id"]

    note = await client.post(
        "/api/notes",
        json={"title": "Tagged", "content_json": "{}"},
        headers=h,
    )
    assert note.status_code == 201, note.text
    note_id = note.json()["id"]

    att = await client.post(f"/api/notes/{note_id}/tags/{child_id}", headers=h)
    assert att.status_code == 200, att.text
    assert child_id in att.json().get("tag_ids", [])

    counts = await client.get("/api/tags/counts", headers=h)
    assert counts.status_code == 200, counts.text
    rows = counts.json()
    assert isinstance(rows, list) and len(rows) >= 2
    by_id = {str(r["tag_id"]): r["count"] for r in rows}
    assert by_id.get(child_id, 0) >= 1, rows
    assert by_id.get(parent_id, 0) >= 1, rows

    filtered_child = await client.get(f"/api/notes?tag_id={child_id}", headers=h)
    assert filtered_child.status_code == 200, filtered_child.text
    ids = {n["id"] for n in filtered_child.json()}
    assert note_id in ids

    filtered_parent = await client.get(f"/api/notes?tag_id={parent_id}", headers=h)
    assert filtered_parent.status_code == 200, filtered_parent.text
    ids_p = {n["id"] for n in filtered_parent.json()}
    assert note_id in ids_p


async def test_notes_filter_multiple_tags_or_union(client: AsyncClient) -> None:
    """Несколько tag_id в запросе: заметки с любой из меток (объединение поддеревьев)."""
    h = await _auth_headers(client, email="multitag@example.com", password="password99")

    a = await client.post("/api/tags", json={"name": "TagA"}, headers=h)
    assert a.status_code == 201, a.text
    a_id = a.json()["id"]
    b = await client.post("/api/tags", json={"name": "TagB"}, headers=h)
    assert b.status_code == 201, b.text
    b_id = b.json()["id"]

    n1 = await client.post("/api/notes", json={"title": "One", "content_json": "{}"}, headers=h)
    assert n1.status_code == 201, n1.text
    n1_id = n1.json()["id"]
    n2 = await client.post("/api/notes", json={"title": "Two", "content_json": "{}"}, headers=h)
    assert n2.status_code == 201, n2.text
    n2_id = n2.json()["id"]

    r1 = await client.post(f"/api/notes/{n1_id}/tags/{a_id}", headers=h)
    assert r1.status_code == 200, r1.text
    r2 = await client.post(f"/api/notes/{n2_id}/tags/{b_id}", headers=h)
    assert r2.status_code == 200, r2.text

    both = await client.get(
        "/api/notes",
        params=[("tag_id", a_id), ("tag_id", b_id)],
        headers=h,
    )
    assert both.status_code == 200, both.text
    got = {n["id"] for n in both.json()}
    assert got == {n1_id, n2_id}
