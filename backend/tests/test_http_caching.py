"""Условные запросы: ETag/Cache-Control у вложений и публичной заметки."""

from httpx import AsyncClient


async def _auth(client: AsyncClient, email: str) -> dict[str, str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password99", "display_name": "C"},
    )
    assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": "password99"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _note(client: AsyncClient, headers: dict[str, str], title: str) -> str:
    r = await client.post(
        "/api/notes", json={"title": title, "content_json": "{}"}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_attachment_download_is_cacheable_and_returns_304(client: AsyncClient) -> None:
    h = await _auth(client, "cacheattach@example.com")
    note_id = await _note(client, h, "С вложением")

    up = await client.post(
        f"/api/notes/{note_id}/attachments",
        headers=h,
        files={"file": ("hello.txt", b"payload-bytes", "text/plain")},
    )
    assert up.status_code == 200, up.text
    attachment_id = up.json()["id"]

    first = await client.get(f"/api/attachments/{attachment_id}/file", headers=h)
    assert first.status_code == 200, first.text
    assert first.content == b"payload-bytes"
    etag = first.headers["etag"]
    assert etag
    cache_control = first.headers["cache-control"]
    assert "immutable" in cache_control
    assert "max-age=31536000" in cache_control
    assert "private" in cache_control

    cached = await client.get(
        f"/api/attachments/{attachment_id}/file",
        headers={**h, "If-None-Match": etag},
    )
    assert cached.status_code == 304, cached.text
    assert cached.content == b""
    assert cached.headers["etag"] == etag

    # Другой ETag — отдаём тело заново.
    stale = await client.get(
        f"/api/attachments/{attachment_id}/file",
        headers={**h, "If-None-Match": '"not-the-same"'},
    )
    assert stale.status_code == 200, stale.text
    assert stale.content == b"payload-bytes"

    # Условный запрос не подменяет проверку доступа.
    other = await _auth(client, "cachestranger@example.com")
    denied = await client.get(
        f"/api/attachments/{attachment_id}/file",
        headers={**other, "If-None-Match": etag},
    )
    assert denied.status_code == 403, denied.text


async def test_public_note_etag_changes_after_edit(client: AsyncClient) -> None:
    h = await _auth(client, "cachepublic@example.com")
    note_id = await _note(client, h, "Публичная")
    link = await client.put(
        f"/api/notes/{note_id}/public-link", json={"role": "editor"}, headers=h
    )
    assert link.status_code == 200, link.text
    token = link.json()["token"]

    first = await client.get(f"/api/public/notes/{token}")
    assert first.status_code == 200, first.text
    etag = first.headers["etag"]
    assert "must-revalidate" in first.headers["cache-control"]

    cached = await client.get(
        f"/api/public/notes/{token}", headers={"If-None-Match": etag}
    )
    assert cached.status_code == 304, cached.text
    assert cached.content == b""

    patched = await client.patch(
        f"/api/public/notes/{token}", json={"title": "Публичная 2"}
    )
    assert patched.status_code == 200, patched.text

    after = await client.get(
        f"/api/public/notes/{token}", headers={"If-None-Match": etag}
    )
    assert after.status_code == 200, after.text
    assert after.headers["etag"] != etag
    assert after.json()["note"]["title"] == "Публичная 2"


async def test_public_habits_etag(client: AsyncClient) -> None:
    h = await _auth(client, "cachehabits@example.com")
    created = await client.post(
        "/api/habits",
        json={"title": "Зарядка", "weekdays": [1, 2, 3, 4, 5], "target_days": 5},
        headers=h,
    )
    assert created.status_code == 201, created.text
    link = await client.put("/api/habits/public-link", headers=h)
    assert link.status_code == 200, link.text
    token = link.json()["token"]

    first = await client.get(f"/api/public/habits/{token}")
    assert first.status_code == 200, first.text
    etag = first.headers["etag"]
    assert first.json()["habits"][0]["title"] == "Зарядка"

    cached = await client.get(
        f"/api/public/habits/{token}", headers={"If-None-Match": etag}
    )
    assert cached.status_code == 304, cached.text

    renamed = await client.patch(
        f"/api/habits/{created.json()['id']}", json={"title": "Бег"}, headers=h
    )
    assert renamed.status_code == 200, renamed.text

    after = await client.get(
        f"/api/public/habits/{token}", headers={"If-None-Match": etag}
    )
    assert after.status_code == 200, after.text
    assert after.headers["etag"] != etag
