"""exclude_folder_id в /api/tags/counts — области как у списка заметок."""

from httpx import AsyncClient


async def _headers(client: AsyncClient, email: str = "tagexcl@test.com") -> dict[str, str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password99", "display_name": "T"},
    )
    assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": "password99"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_tag_counts_respects_exclude_folder_globally(client: AsyncClient) -> None:
    """Без folder_id счётчик метки не считает заметки только в исключаемой папке."""
    h = await _headers(client)

    keep = await client.post("/api/folders", json={"name": "K"}, headers=h)
    assert keep.status_code == 201, keep.text
    keep_id = keep.json()["id"]
    hide = await client.post("/api/folders", json={"name": "H"}, headers=h)
    assert hide.status_code == 201, hide.text
    hide_id = hide.json()["id"]

    tg = await client.post("/api/tags", json={"name": "Tg"}, headers=h)
    assert tg.status_code == 201, tg.text
    tg_id = tg.json()["id"]

    nk = await client.post(
        "/api/notes",
        json={"title": "n1", "content_json": "{}", "folder_id": keep_id},
        headers=h,
    )
    assert nk.status_code == 201, nk.text
    nk_id = nk.json()["id"]
    nh = await client.post(
        "/api/notes",
        json={"title": "n2", "content_json": "{}", "folder_id": hide_id},
        headers=h,
    )
    assert nh.status_code == 201, nh.text
    nh_id = nh.json()["id"]

    ok_att = await client.post(f"/api/notes/{nk_id}/tags/{tg_id}", headers=h)
    assert ok_att.status_code == 200, ok_att.text
    h_att = await client.post(f"/api/notes/{nh_id}/tags/{tg_id}", headers=h)
    assert h_att.status_code == 200, h_att.text

    raw = await client.get("/api/tags/counts", headers=h)
    assert raw.status_code == 200, raw.text
    by_full = _count_map(raw.json()).get(str(tg_id))
    assert by_full == 2, raw.json()

    ex = await client.get(
        "/api/tags/counts", params={"exclude_folder_id": hide_id}, headers=h
    )
    assert ex.status_code == 200, ex.text
    by_hidden = _count_map(ex.json()).get(str(tg_id))
    assert by_hidden == 1, ex.json()


def _count_map(rows: object) -> dict[str, int]:
    m: dict[str, int] = {}
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        tid = row.get("tag_id")
        cnt = row.get("count")
        if tid is None or cnt is None:
            continue
        m[str(tid)] = int(cnt)
    return m
