"""Раздел карт: только mindmap-блоки из доступных заметок."""

import json

from httpx import AsyncClient


def _scene(root_text: str, children: list | None = None) -> str:
    return json.dumps(
        {
            "root": {"data": {"text": root_text}, "children": children or []},
            "theme": {"template": "classic", "config": {}},
            "layout": "mindMap",
            "config": {},
            "view": None,
        },
        ensure_ascii=False,
    )


def _doc(*roots: str) -> str:
    blocks = [
        {
            "type": "mindmapBlock",
            "attrs": {"scene": _scene(root), "collapsed": False},
        }
        for root in roots
    ]
    return json.dumps({"type": "doc", "content": blocks}, ensure_ascii=False)


def _excalidraw_doc(text: str) -> str:
    scene = json.dumps(
        {
            "type": "excalidraw",
            "version": 2,
            "elements": [{"id": "t1", "type": "text", "text": text, "isDeleted": False}],
            "appState": {},
            "files": {},
        },
        ensure_ascii=False,
    )
    return json.dumps(
        {
            "type": "doc",
            "content": [{"type": "excalidrawBlock", "attrs": {"scene": scene, "collapsed": False}}],
        },
        ensure_ascii=False,
    )


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


async def test_mindmaps_forbidden_when_admin_revokes(client: AsyncClient) -> None:
    admin = await _register_login(client, "tagtest@example.com")
    guest = await _register_login(client, "map.guest@example.com")
    guest_id = await _user_id(client, admin, "map.guest@example.com")
    patched = await client.patch(
        f"/api/admin/users/{guest_id}",
        headers=admin,
        json={"can_use_schemas": False},
    )
    assert patched.status_code == 200, patched.text
    denied = await client.get("/api/mindmaps", headers=guest)
    assert denied.status_code == 403


async def test_mindmaps_only_from_accessible_notes_and_ignore_schemas(client: AsyncClient) -> None:
    owner = await _register_login(client, "tagtest@example.com")
    other = await _register_login(client, "map.other@example.com")

    mine = await client.post(
        "/api/notes",
        headers=owner,
        json={"title": "Моя карта", "content_json": _doc("Отпуск")},
    )
    assert mine.status_code == 201, mine.text
    hidden = await client.post(
        "/api/notes",
        headers=other,
        json={"title": "Чужая карта", "content_json": _doc("секрет")},
    )
    assert hidden.status_code == 201, hidden.text
    schema_only = await client.post(
        "/api/notes",
        headers=owner,
        json={"title": "Только схема", "content_json": _excalidraw_doc("чертёж")},
    )
    assert schema_only.status_code == 201, schema_only.text

    listed = await client.get("/api/mindmaps", headers=owner)
    assert listed.status_code == 200, listed.text
    captions = [row["caption"] for row in listed.json()]
    assert "Отпуск" in captions
    assert "секрет" not in captions
    assert "чертёж" not in captions
    assert all(row["note_title"] != "Только схема" for row in listed.json())

    schemas = await client.get("/api/schemas", headers=owner)
    assert schemas.status_code == 200, schemas.text
    assert "чертёж" in [row["caption"] for row in schemas.json()]
    assert "Отпуск" not in [row["caption"] for row in schemas.json()]


async def test_mindmap_title_patch_writes_back_to_source_note(client: AsyncClient) -> None:
    owner = await _register_login(client, "tagtest@example.com")
    doc = json.dumps(
        {
            "type": "doc",
            "content": [
                {
                    "type": "mindmapBlock",
                    "attrs": {
                        "scene": _scene("Главная", [{"data": {"text": "лист"}, "children": []}]),
                        "collapsed": False,
                        "title": "Старое имя",
                    },
                }
            ],
        },
        ensure_ascii=False,
    )
    created = await client.post(
        "/api/notes",
        headers=owner,
        json={"title": "Заметка с картой", "content_json": doc},
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]

    listed = await client.get("/api/mindmaps", headers=owner)
    assert listed.status_code == 200, listed.text
    row = next(x for x in listed.json() if x["note_id"] == note_id)
    assert row["caption"] == "Старое имя"

    patched = await client.patch(
        f"/api/mindmaps/{note_id}/0",
        headers=owner,
        json={"title": "Новая карта"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["caption"] == "Новая карта"

    note = await client.get(f"/api/notes/{note_id}", headers=owner)
    assert note.status_code == 200, note.text
    saved = json.loads(note.json()["content_json"])
    assert saved["content"][0]["attrs"]["title"] == "Новая карта"
    assert "лист" in saved["content"][0]["attrs"]["scene"]


async def test_mindmap_list_includes_note_tag_names(client: AsyncClient) -> None:
    owner = await _register_login(client, "tagtest@example.com")
    created = await client.post(
        "/api/notes",
        headers=owner,
        json={"title": "С тегом", "content_json": _doc("Проект")},
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]
    tag = await client.post("/api/tags", json={"name": "Работа"}, headers=owner)
    assert tag.status_code == 201, tag.text
    attached = await client.post(f"/api/notes/{note_id}/tags/{tag.json()['id']}", headers=owner)
    assert attached.status_code == 200, attached.text

    listed = await client.get("/api/mindmaps", headers=owner)
    assert listed.status_code == 200, listed.text
    row = next(x for x in listed.json() if x["note_id"] == note_id)
    assert "Работа" in row["tag_names"]
