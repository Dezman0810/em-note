"""Админ забирает расшаренную заметку себе как создатель."""

from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> tuple[dict[str, str], str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password99", "display_name": "U"},
    )
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]
    r = await client.post("/api/auth/login", json={"email": email, "password": "password99"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, user_id


async def test_non_admin_cannot_take_ownership(client: AsyncClient) -> None:
    h_owner, _ = await _register_and_login(client, "owner.take@example.com")
    h_bee, bee_id = await _register_and_login(client, "bee.take@example.com")
    n = await client.post("/api/notes", json={"title": "X", "content_json": "{}"}, headers=h_owner)
    note_id = n.json()["id"]
    await client.post(
        f"/api/notes/{note_id}/shares",
        headers=h_owner,
        json={"shared_with_user_id": bee_id, "role": "editor"},
    )
    taken = await client.post(f"/api/notes/{note_id}/take-ownership", headers=h_bee)
    assert taken.status_code == 403


async def test_admin_takes_ownership_then_controls_access(client: AsyncClient) -> None:
    h_owner, owner_id = await _register_and_login(client, "author.take@example.com")
    h_admin, admin_id = await _register_and_login(client, "tagtest@example.com")

    folder = await client.post("/api/folders", json={"name": "Авторская"}, headers=h_owner)
    assert folder.status_code == 201, folder.text
    folder_id = folder.json()["id"]

    n = await client.post(
        "/api/notes",
        json={"title": "Общая", "content_json": "{}", "folder_id": folder_id},
        headers=h_owner,
    )
    assert n.status_code == 201, n.text
    note_id = n.json()["id"]
    assert n.json()["owner_id"] == owner_id

    sh = await client.post(
        f"/api/notes/{note_id}/shares",
        headers=h_owner,
        json={"shared_with_user_id": admin_id, "role": "editor"},
    )
    assert sh.status_code == 201, sh.text

    taken = await client.post(f"/api/notes/{note_id}/take-ownership", headers=h_admin)
    assert taken.status_code == 200, taken.text
    body = taken.json()
    assert body["owner_id"] == admin_id
    assert body["my_access"] == "owner"
    assert body["folder_id"] is None

    shares = await client.get(f"/api/notes/{note_id}/shares", headers=h_admin)
    assert shares.status_code == 200
    rows = shares.json()
    assert len(rows) == 1
    assert rows[0]["shared_with_user_id"] == owner_id
    assert rows[0]["role"] == "editor"
    share_id = rows[0]["id"]

    forbidden = await client.delete(f"/api/notes/{note_id}", headers=h_owner)
    assert forbidden.status_code == 403

    still_there = await client.get("/api/notes", headers=h_owner)
    row = next(x for x in still_there.json() if x["id"] == note_id)
    assert row["my_access"] == "edit"
    assert row["folder_id"] == folder_id

    demote = await client.patch(
        f"/api/notes/{note_id}/shares/{share_id}",
        headers=h_admin,
        json={"role": "viewer"},
    )
    assert demote.status_code == 200
    assert demote.json()["role"] == "viewer"
    after_demote = await client.get(f"/api/notes/{note_id}", headers=h_owner)
    assert after_demote.json()["my_access"] == "read"

    gone = await client.delete(f"/api/notes/{note_id}/shares/{share_id}", headers=h_admin)
    assert gone.status_code == 204
    lst = await client.get("/api/notes", headers=h_owner)
    assert all(x["id"] != note_id for x in lst.json())

    trash = await client.delete(f"/api/notes/{note_id}", headers=h_admin)
    assert trash.status_code == 204


async def test_admin_cannot_take_unshared_note(client: AsyncClient) -> None:
    h_owner, _ = await _register_and_login(client, "solo.owner@example.com")
    h_admin, _ = await _register_and_login(client, "tagtest@example.com")
    n = await client.post("/api/notes", json={"title": "Личная", "content_json": "{}"}, headers=h_owner)
    taken = await client.post(f"/api/notes/{n.json()['id']}/take-ownership", headers=h_admin)
    assert taken.status_code == 403
