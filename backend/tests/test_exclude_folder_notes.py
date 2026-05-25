"""Фильтр exclude_folder_id в списке заметок."""

from httpx import AsyncClient


async def _headers(client: AsyncClient, email: str = "fldex@test.com") -> dict[str, str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password99", "display_name": "Fld Ex"},
    )
    assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": "password99"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_exclude_folder_removes_own_notes(client: AsyncClient) -> None:
    h = await _headers(client)

    a = await client.post("/api/folders", json={"name": "Keep"}, headers=h)
    assert a.status_code == 201, a.text
    keep_id = a.json()["id"]
    b = await client.post("/api/folders", json={"name": "Hide"}, headers=h)
    assert b.status_code == 201, b.text
    hide_id = b.json()["id"]

    nk = await client.post(
        "/api/notes", json={"title": "In keep", "content_json": "{}", "folder_id": keep_id}, headers=h
    )
    assert nk.status_code == 201, nk.text
    nk_id = nk.json()["id"]
    nh = await client.post(
        "/api/notes", json={"title": "In hide", "content_json": "{}", "folder_id": hide_id}, headers=h
    )
    assert nh.status_code == 201, nh.text
    nh_id = nh.json()["id"]

    r = await client.get("/api/notes", params={"exclude_folder_id": hide_id}, headers=h)
    assert r.status_code == 200, r.text
    ids = {n["id"] for n in r.json()}
    assert nk_id in ids
    assert nh_id not in ids


async def test_exclude_folder_keeps_unfoldered_notes(client: AsyncClient) -> None:
    """Без папки (folder_id NULL): исключить «папочные» — не фильтровать из-за UNKNOWN в SQL IN."""
    h = await _headers(client, email="unfldex@test.com")

    b = await client.post("/api/folders", json={"name": "Box"}, headers=h)
    assert b.status_code == 201, b.text
    box_id = b.json()["id"]

    n_box = await client.post(
        "/api/notes", json={"title": "В папке", "content_json": "{}", "folder_id": box_id}, headers=h
    )
    assert n_box.status_code == 201, n_box.text
    n_box_id = n_box.json()["id"]

    n_root = await client.post(
        "/api/notes", json={"title": "Без папки", "content_json": "{}"}, headers=h
    )
    assert n_root.status_code == 201, n_root.text
    n_root_id = n_root.json()["id"]

    r = await client.get("/api/notes", params={"exclude_folder_id": box_id}, headers=h)
    assert r.status_code == 200, r.text
    ids = {n["id"] for n in r.json()}
    assert n_root_id in ids
    assert n_box_id not in ids
