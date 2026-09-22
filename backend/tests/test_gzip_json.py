"""Сжатие JSON-ответов: крупные заметки едут gzip, бинарные вложения — как есть."""

import json

from httpx import AsyncClient


async def _auth(client: AsyncClient, email: str) -> dict[str, str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password99", "display_name": "G"},
    )
    assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": "password99"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_large_note_json_is_gzipped(client: AsyncClient) -> None:
    h = await _auth(client, "gzipnote@example.com")
    big = json.dumps(
        {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "строка " * 40}]}
                for _ in range(120)
            ],
        }
    )
    created = await client.post(
        "/api/notes", json={"title": "Большая", "content_json": big}, headers=h
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]

    r = await client.get(
        f"/api/notes/{note_id}", headers={**h, "Accept-Encoding": "gzip"}
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-encoding"] == "gzip"
    assert "Accept-Encoding" in r.headers.get("vary", "")
    # httpx распаковывает прозрачно: содержимое должно остаться прежним.
    assert r.json()["content_json"] == big
    assert int(r.headers["content-length"]) < len(big)


async def test_small_json_and_attachment_are_not_gzipped(client: AsyncClient) -> None:
    h = await _auth(client, "gzipsmall@example.com")

    me = await client.get("/api/auth/me", headers={**h, "Accept-Encoding": "gzip"})
    assert me.status_code == 200, me.text
    assert "content-encoding" not in me.headers

    created = await client.post(
        "/api/notes", json={"title": "С файлом", "content_json": "{}"}, headers=h
    )
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]
    up = await client.post(
        f"/api/notes/{note_id}/attachments",
        headers=h,
        files={"file": ("a.bin", b"binary-payload" * 200, "application/octet-stream")},
    )
    assert up.status_code == 200, up.text

    got = await client.get(
        f"/api/attachments/{up.json()['id']}/file",
        headers={**h, "Accept-Encoding": "gzip"},
    )
    assert got.status_code == 200, got.text
    assert "content-encoding" not in got.headers
    assert got.content == b"binary-payload" * 200
