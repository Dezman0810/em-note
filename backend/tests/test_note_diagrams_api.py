"""Раздел draw.io-диаграмм: только c4Block из доступных заметок."""

import json

from httpx import AsyncClient

DEFAULT_DRAWIO = """<mxfile host="Em-Note" agent="Em-Note" version="22.1.0" type="device">
  <diagram id="page-1" name="CRM">
    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="827" pageHeight="1169" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="2" value="CRM" vertex="1" parent="1">
          <mxGeometry x="320" y="240" width="120" height="60" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""


def _drawio_doc(*titles: str) -> str:
    blocks = []
    for title in titles:
        xml = DEFAULT_DRAWIO.replace('name="CRM"', f'name="{title}"', 1)
        blocks.append(
            {
                "type": "c4Block",
                "attrs": {"scene": xml, "collapsed": False, "title": title},
            }
        )
    return json.dumps({"type": "doc", "content": blocks}, ensure_ascii=False)


def _mindmap_doc(root_text: str) -> str:
    scene = json.dumps(
        {
            "root": {"data": {"text": root_text}, "children": []},
            "theme": {"template": "classic", "config": {}},
            "layout": "mindMap",
            "config": {},
            "view": None,
        },
        ensure_ascii=False,
    )
    return json.dumps(
        {
            "type": "doc",
            "content": [{"type": "mindmapBlock", "attrs": {"scene": scene, "collapsed": False}}],
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


async def test_diagrams_forbidden_when_admin_revokes(client: AsyncClient) -> None:
    admin = await _register_login(client, "tagtest@example.com")
    guest = await _register_login(client, "diagram.guest@example.com")
    guest_id = await _user_id(client, admin, "diagram.guest@example.com")
    patched = await client.patch(
        f"/api/admin/users/{guest_id}",
        headers=admin,
        json={"can_use_schemas": False},
    )
    assert patched.status_code == 200, patched.text
    denied = await client.get("/api/diagrams", headers=guest)
    assert denied.status_code == 403


async def test_diagrams_only_from_accessible_notes_and_ignore_other_blocks(client: AsyncClient) -> None:
    owner = await _register_login(client, "tagtest@example.com")
    other = await _register_login(client, "diagram.other@example.com")

    mine = await client.post(
        "/api/notes",
        headers=owner,
        json={"title": "Моя диаграмма", "content_json": _drawio_doc("CRM")},
    )
    assert mine.status_code == 201, mine.text
    hidden = await client.post(
        "/api/notes",
        headers=other,
        json={"title": "Чужая диаграмма", "content_json": _drawio_doc("секрет")},
    )
    assert hidden.status_code == 201, hidden.text
    map_only = await client.post(
        "/api/notes",
        headers=owner,
        json={"title": "Только карта", "content_json": _mindmap_doc("узел")},
    )
    assert map_only.status_code == 201, map_only.text

    listed = await client.get("/api/diagrams", headers=owner)
    assert listed.status_code == 200, listed.text
    captions = [row["caption"] for row in listed.json()]
    assert "CRM" in captions
    assert "секрет" not in captions
    assert "узел" not in captions
    assert all(row["note_title"] != "Только карта" for row in listed.json())

    mindmaps = await client.get("/api/mindmaps", headers=owner)
    assert mindmaps.status_code == 200, mindmaps.text
    assert "узел" in [row["caption"] for row in mindmaps.json()]
    assert "CRM" not in [row["caption"] for row in mindmaps.json()]


async def test_diagram_title_patch_writes_back_to_source_note(client: AsyncClient) -> None:
    owner = await _register_login(client, "tagtest@example.com")
    doc = json.dumps(
        {
            "type": "doc",
            "content": [
                {
                    "type": "c4Block",
                    "attrs": {
                        "scene": DEFAULT_DRAWIO,
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
        json={"title": "Заметка с диаграммой", "content_json": doc},
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]

    listed = await client.get("/api/diagrams", headers=owner)
    assert listed.status_code == 200, listed.text
    row = next(x for x in listed.json() if x["note_id"] == note_id)
    assert row["caption"] == "Старое имя"

    patched = await client.patch(
        f"/api/diagrams/{note_id}/0",
        headers=owner,
        json={"title": "Новая диаграмма"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["caption"] == "Новая диаграмма"

    note = await client.get(f"/api/notes/{note_id}", headers=owner)
    assert note.status_code == 200, note.text
    saved = json.loads(note.json()["content_json"])
    assert saved["content"][0]["attrs"]["title"] == "Новая диаграмма"
    assert "<mxfile" in saved["content"][0]["attrs"]["scene"]
