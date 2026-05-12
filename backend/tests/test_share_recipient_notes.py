"""Шаринг: получатель видит общую заметку в GET /api/notes без 500."""

from httpx import AsyncClient

SHARED_ACCESS_EMAIL_LABEL = "Доступ по email"


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


async def test_recipient_gets_shared_note_in_list(client: AsyncClient) -> None:
    # Один аккаунт с правом создания заметок: см. conftest monkeypatch settings.admin_email
    h_owner, _ = await _register_and_login(client, "tagtest@example.com")
    h_bee, bee_id = await _register_and_login(client, "sharebee@example.com")

    n = await client.post("/api/notes", json={"title": "Shared", "content_json": "{}"}, headers=h_owner)
    assert n.status_code == 201, n.text
    note_id = n.json()["id"]

    sh = await client.post(
        f"/api/notes/{note_id}/shares",
        headers=h_owner,
        json={"shared_with_user_id": bee_id, "role": "viewer"},
    )
    assert sh.status_code == 201, sh.text

    lst = await client.get("/api/notes", headers=h_bee)
    assert lst.status_code == 200, lst.text
    body = lst.json()
    assert len(body) >= 1
    match = next((x for x in body if x["id"] == note_id), None)
    assert match is not None
    assert match["my_access"] == "read"
    assert match["title"] == "Shared"

    tags_bee = await client.get("/api/tags", headers=h_bee)
    assert tags_bee.status_code == 200, tags_bee.text
    by_name = {t["name"]: t["id"] for t in tags_bee.json()}
    assert SHARED_ACCESS_EMAIL_LABEL in by_name
    assert str(by_name[SHARED_ACCESS_EMAIL_LABEL]) in {str(x) for x in match["tag_ids"]}

    counts = await client.get("/api/tags/note-counts", headers=h_bee)
    assert counts.status_code == 200, counts.text


async def test_invite_email_linked_after_register_lists_note(client: AsyncClient) -> None:
    """Пока пользователя не было — шар только по email; после регистрации заметка появляется."""
    h_owner, _ = await _register_and_login(client, "tagtest@example.com")
    inbox = "laterbee@example.com"

    n = await client.post("/api/notes", json={"title": "Invite", "content_json": "{}"}, headers=h_owner)
    assert n.status_code == 201, n.text
    note_id = n.json()["id"]

    sh = await client.post(
        f"/api/notes/{note_id}/shares",
        headers=h_owner,
        json={"invite_email": inbox, "role": "viewer"},
    )
    assert sh.status_code == 201, sh.text

    rb = await client.post(
        "/api/auth/register",
        json={"email": inbox, "password": "password99", "display_name": "Bee"},
    )
    assert rb.status_code == 201, rb.text
    rl = await client.post("/api/auth/login", json={"email": inbox, "password": "password99"})
    assert rl.status_code == 200, rl.text
    h_new = {"Authorization": f"Bearer {rl.json()['access_token']}"}

    lst = await client.get("/api/notes", headers=h_new)
    assert lst.status_code == 200, lst.text
    row = next((x for x in lst.json() if x["id"] == note_id), None)
    assert row is not None
    tags_new = await client.get("/api/tags", headers=h_new)
    assert tags_new.status_code == 200, tags_new.text
    by_name = {t["name"]: t["id"] for t in tags_new.json()}
    assert SHARED_ACCESS_EMAIL_LABEL in by_name
    assert str(by_name[SHARED_ACCESS_EMAIL_LABEL]) in {str(x) for x in row["tag_ids"]}


async def test_owner_can_patch_share_role(client: AsyncClient) -> None:
    h_owner, _ = await _register_and_login(client, "tagtest@example.com")
    h_bee, bee_id = await _register_and_login(client, "rolepatchbee@example.com")
    n = await client.post("/api/notes", json={"title": "Role note", "content_json": "{}"}, headers=h_owner)
    assert n.status_code == 201, n.text
    note_id = n.json()["id"]
    sh = await client.post(
        f"/api/notes/{note_id}/shares",
        headers=h_owner,
        json={"shared_with_user_id": bee_id, "role": "viewer"},
    )
    assert sh.status_code == 201, sh.text
    sid = sh.json()["id"]
    assert sh.json()["role"] == "viewer"
    p = await client.patch(
        f"/api/notes/{note_id}/shares/{sid}",
        headers=h_owner,
        json={"role": "editor"},
    )
    assert p.status_code == 200, p.text
    assert p.json()["role"] == "editor"
    lst_bee = await client.get("/api/notes", headers=h_bee)
    assert lst_bee.status_code == 200
    row = next((x for x in lst_bee.json() if x["id"] == note_id), None)
    assert row is not None
    assert row["my_access"] == "edit"
