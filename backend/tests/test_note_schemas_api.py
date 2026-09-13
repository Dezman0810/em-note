"""Раздел схем: только из доступных заметок, правки пишутся в ту же заметку."""

import json

from httpx import AsyncClient


def _scene(text: str) -> str:
    return json.dumps(
        {
            "type": "excalidraw",
            "version": 2,
            "elements": [{"id": "t1", "type": "text", "text": text, "isDeleted": False}],
            "appState": {},
            "files": {},
        },
        ensure_ascii=False,
    )


def _doc(*captions: str) -> str:
    blocks = [
        {
            "type": "excalidrawBlock",
            "attrs": {"scene": _scene(caption), "collapsed": False},
        }
        for caption in captions
    ]
    return json.dumps({"type": "doc", "content": blocks}, ensure_ascii=False)


async def _register_login(client: AsyncClient, email: str) -> dict[str, str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password99", "display_name": "U"},
    )
    assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": "password99"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _user_id(client: AsyncClient, admin: dict[str, str], email: str) -> str:
    users = await client.get("/api/admin/users", headers=admin)
    assert users.status_code == 200, users.text
    return next(u["id"] for u in users.json() if u["email"] == email)


async def test_schemas_forbidden_when_admin_revokes(client: AsyncClient) -> None:
    admin = await _register_login(client, "tagtest@example.com")
    guest = await _register_login(client, "schema.guest@example.com")
    guest_id = await _user_id(client, admin, "schema.guest@example.com")
    patched = await client.patch(
        f"/api/admin/users/{guest_id}",
        headers=admin,
        json={"can_use_schemas": False},
    )
    assert patched.status_code == 200, patched.text
    denied = await client.get("/api/schemas", headers=guest)
    assert denied.status_code == 403


async def test_schemas_only_from_accessible_notes(client: AsyncClient) -> None:
    owner = await _register_login(client, "tagtest@example.com")
    other = await _register_login(client, "schema.other@example.com")

    mine = await client.post(
        "/api/notes",
        headers=owner,
        json={"title": "Мой план", "content_json": _doc("кухня")},
    )
    assert mine.status_code == 201, mine.text
    hidden = await client.post(
        "/api/notes",
        headers=other,
        json={"title": "Чужой чертёж", "content_json": _doc("секрет")},
    )
    assert hidden.status_code == 201, hidden.text
    plain = await client.post(
        "/api/notes",
        headers=owner,
        json={"title": "Без схемы", "content_json": json.dumps({"type": "doc", "content": []})},
    )
    assert plain.status_code == 201, plain.text

    listed = await client.get("/api/schemas", headers=owner)
    assert listed.status_code == 200, listed.text
    captions = [row["caption"] for row in listed.json()]
    assert "кухня" in captions
    assert "секрет" not in captions
    assert all(row["note_title"] != "Без схемы" for row in listed.json())


async def test_shared_note_schema_visible_and_viewer_cannot_edit(client: AsyncClient) -> None:
    owner = await _register_login(client, "tagtest@example.com")
    guest = await _register_login(client, "schema.viewer@example.com")
    guest_id = await _user_id(client, owner, "schema.viewer@example.com")

    created = await client.post(
        "/api/notes",
        headers=owner,
        json={"title": "Общий план", "content_json": _doc("дом", "двор")},
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]
    share = await client.post(
        f"/api/notes/{note_id}/shares",
        headers=owner,
        json={"shared_with_user_id": guest_id, "role": "viewer"},
    )
    assert share.status_code == 201, share.text

    listed = await client.get("/api/schemas", headers=guest)
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert {row["caption"] for row in rows} == {"дом", "двор"}
    assert all(row["note_id"] == note_id for row in rows)
    assert all(row["can_edit"] is False for row in rows)

    forbidden = await client.patch(
        f"/api/schemas/{note_id}/0",
        headers=guest,
        json={"scene": _scene("взлом")},
    )
    assert forbidden.status_code == 403

    other_note = await client.post(
        "/api/notes",
        headers=owner,
        json={"title": "Личное", "content_json": _doc("не для гостя")},
    )
    assert other_note.status_code == 201, other_note.text
    listed_again = await client.get("/api/schemas", headers=guest)
    captions = {row["caption"] for row in listed_again.json()}
    assert "не для гостя" not in captions
    assert "дом" in captions


async def test_schema_patch_writes_back_to_source_note(client: AsyncClient) -> None:
    owner = await _register_login(client, "tagtest@example.com")
    created = await client.post(
        "/api/notes",
        headers=owner,
        json={"title": "Две схемы", "content_json": _doc("первая", "вторая")},
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]

    detail = await client.get(f"/api/schemas/{note_id}/1", headers=owner)
    assert detail.status_code == 200, detail.text
    assert detail.json()["caption"] == "вторая"

    patched = await client.patch(
        f"/api/schemas/{note_id}/1",
        headers=owner,
        json={"scene": _scene("вторая-обновлена")},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["caption"] == "вторая-обновлена"

    note = await client.get(f"/api/notes/{note_id}", headers=owner)
    assert note.status_code == 200, note.text
    doc = json.loads(note.json()["content_json"])
    scenes = [block["attrs"]["scene"] for block in doc["content"]]
    assert "первая" in scenes[0]
    assert "вторая-обновлена" in scenes[1]
    assert "первая" not in scenes[1]


async def test_schema_title_attr_used_as_caption_and_can_be_renamed(client: AsyncClient) -> None:
    owner = await _register_login(client, "tagtest@example.com")
    doc = json.dumps(
        {
            "type": "doc",
            "content": [
                {
                    "type": "excalidrawBlock",
                    "attrs": {
                        "scene": _scene("текст на холсте"),
                        "collapsed": False,
                        "title": "План кухни",
                    },
                }
            ],
        },
        ensure_ascii=False,
    )
    created = await client.post(
        "/api/notes",
        headers=owner,
        json={"title": "С названием", "content_json": doc},
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]

    listed = await client.get("/api/schemas", headers=owner)
    assert listed.status_code == 200, listed.text
    row = next(x for x in listed.json() if x["note_id"] == note_id)
    assert row["caption"] == "План кухни"

    patched = await client.patch(
        f"/api/schemas/{note_id}/0",
        headers=owner,
        json={"title": "Кухня v2"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["caption"] == "Кухня v2"
    assert "текст на холсте" in patched.json()["scene"]

    note = await client.get(f"/api/notes/{note_id}", headers=owner)
    assert note.status_code == 200, note.text
    saved = json.loads(note.json()["content_json"])
    assert saved["content"][0]["attrs"]["title"] == "Кухня v2"


async def test_schema_list_includes_note_tag_names(client: AsyncClient) -> None:
    owner = await _register_login(client, "tagtest@example.com")
    created = await client.post(
        "/api/notes",
        headers=owner,
        json={"title": "С тегом", "content_json": _doc("план")},
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]
    tag = await client.post("/api/tags", json={"name": "Дом"}, headers=owner)
    assert tag.status_code == 201, tag.text
    attached = await client.post(f"/api/notes/{note_id}/tags/{tag.json()['id']}", headers=owner)
    assert attached.status_code == 200, attached.text

    listed = await client.get("/api/schemas", headers=owner)
    assert listed.status_code == 200, listed.text
    row = next(x for x in listed.json() if x["note_id"] == note_id)
    assert "Дом" in row["tag_names"]
