"""Проверка счётчиков меток и фильтрации списка заметок по tag_id (включая поддерево)."""

from starlette.testclient import TestClient


def _auth_headers(client: TestClient, email: str = "tagtest@example.com", password: str = "password99") -> dict[str, str]:
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "Tag Test"},
    )
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_tag_counts_and_list_filter_subtree(client: TestClient) -> None:
    h = _auth_headers(client)

    parent = client.post("/api/tags", json={"name": "Parent"}, headers=h)
    assert parent.status_code == 201, parent.text
    parent_id = parent.json()["id"]

    child = client.post(
        "/api/tags",
        json={"name": "Child", "parent_id": parent_id},
        headers=h,
    )
    assert child.status_code == 201, child.text
    child_id = child.json()["id"]

    note = client.post(
        "/api/notes",
        json={"title": "Tagged", "content_json": "{}"},
        headers=h,
    )
    assert note.status_code == 201, note.text
    note_id = note.json()["id"]

    att = client.post(f"/api/notes/{note_id}/tags/{child_id}", headers=h)
    assert att.status_code == 200, att.text
    assert child_id in att.json().get("tag_ids", [])

    counts = client.get("/api/tags/counts", headers=h)
    assert counts.status_code == 200, counts.text
    rows = counts.json()
    assert isinstance(rows, list) and len(rows) >= 2
    by_id = {str(r["tag_id"]): r["count"] for r in rows}
    assert by_id.get(child_id, 0) >= 1, rows
    assert by_id.get(parent_id, 0) >= 1, rows

    filtered_child = client.get(f"/api/notes?tag_id={child_id}", headers=h)
    assert filtered_child.status_code == 200, filtered_child.text
    ids = {n["id"] for n in filtered_child.json()}
    assert note_id in ids

    filtered_parent = client.get(f"/api/notes?tag_id={parent_id}", headers=h)
    assert filtered_parent.status_code == 200, filtered_parent.text
    ids_p = {n["id"] for n in filtered_parent.json()}
    assert note_id in ids_p
