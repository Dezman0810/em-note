"""Открытие заметки в корзине: GET и вспомогательные вызовы владельца не должны отдавать 404."""

from httpx import AsyncClient


async def _auth_headers(
    client: AsyncClient, email: str = "tagtest@example.com", password: str = "password99"
) -> dict[str, str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "Trash Test"},
    )
    assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_owner_can_get_and_list_shares_for_trashed_note(client: AsyncClient) -> None:
    h = await _auth_headers(client)

    created = await client.post(
        "/api/notes",
        json={"title": "In trash", "content_json": "{}"},
        headers=h,
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]

    del_r = await client.delete(f"/api/notes/{note_id}", headers=h)
    assert del_r.status_code == 204, del_r.text

    get_r = await client.get(f"/api/notes/{note_id}", headers=h)
    assert get_r.status_code == 200, get_r.text
    body = get_r.json()
    assert body["id"] == note_id
    assert body["deleted_at"] is not None

    shares_r = await client.get(f"/api/notes/{note_id}/shares", headers=h)
    assert shares_r.status_code == 200, shares_r.text
    assert shares_r.json() == []


async def test_patch_trashed_note_is_rejected(client: AsyncClient) -> None:
    h = await _auth_headers(client)

    created = await client.post(
        "/api/notes",
        json={"title": "Trashed", "content_json": "{}"},
        headers=h,
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]

    await client.delete(f"/api/notes/{note_id}", headers=h)

    patch_r = await client.patch(
        f"/api/notes/{note_id}",
        json={"title": "Nope"},
        headers=h,
    )
    assert patch_r.status_code == 400, patch_r.text


async def test_empty_trash_purges_trashed_notes_and_keeps_live(client: AsyncClient) -> None:
    h = await _auth_headers(client)

    keep_live = await client.post(
        "/api/notes", json={"title": "Live", "content_json": "{}"}, headers=h
    )
    assert keep_live.status_code == 201, keep_live.text
    live_id = keep_live.json()["id"]

    to_trash_a = await client.post(
        "/api/notes", json={"title": "Gone A", "content_json": "{}"}, headers=h
    )
    to_trash_b = await client.post(
        "/api/notes", json={"title": "Gone B", "content_json": "{}"}, headers=h
    )
    assert to_trash_a.status_code == 201, to_trash_a.text
    assert to_trash_b.status_code == 201, to_trash_b.text
    a_id = to_trash_a.json()["id"]
    b_id = to_trash_b.json()["id"]
    assert (await client.delete(f"/api/notes/{a_id}", headers=h)).status_code == 204
    assert (await client.delete(f"/api/notes/{b_id}", headers=h)).status_code == 204

    emptied = await client.delete("/api/notes/trash", headers=h)
    assert emptied.status_code == 204, emptied.text

    trash = await client.get("/api/notes", params={"trash_only": True}, headers=h)
    assert trash.status_code == 200, trash.text
    assert trash.json() == []

    live = await client.get(f"/api/notes/{live_id}", headers=h)
    assert live.status_code == 200, live.text
    assert live.json()["deleted_at"] is None

    gone = await client.get(f"/api/notes/{a_id}", headers=h)
    assert gone.status_code == 404
