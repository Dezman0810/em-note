"""Список заметок не отдаёт полный content_json (тяжёлые сцены Excalidraw)."""

import json

import pytest
from httpx import AsyncClient


async def _auth(client: AsyncClient, email: str = "listcompact@example.com") -> dict[str, str]:
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password99", "display_name": "LC"},
    )
    r = await client.post("/api/auth/login", json={"email": email, "password": "password99"})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_notes_omits_heavy_content_json(client: AsyncClient) -> None:
    h = await _auth(client)
    big_scene = {"type": "doc", "content": [{"type": "paragraph", "content": ["x" * 8000]}]}
    created = await client.post(
        "/api/notes",
        json={
            "title": "Heavy",
            "content_json": json.dumps(big_scene),
            "content_plain": "preview " + ("y" * 2000),
        },
        headers=h,
    )
    assert created.status_code == 201
    note_id = created.json()["id"]

    full = await client.get(f"/api/notes/{note_id}", headers=h)
    assert full.status_code == 200
    assert len(full.json()["content_json"]) > 100

    listed = await client.get("/api/notes", headers=h)
    assert listed.status_code == 200
    row = next(x for x in listed.json() if x["id"] == note_id)
    assert row["content_json"] == "{}"
    assert len(row["content_plain"]) <= 650
    assert "yyyy" in row["content_plain"]
