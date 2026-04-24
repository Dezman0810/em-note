"""Фильтр списка заметок по нескольким папкам (объединение)."""

from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> dict[str, str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password99", "display_name": "F"},
    )
    assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": "password99"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_notes_filter_multiple_folders_or_union(client: AsyncClient) -> None:
    h = await _register_and_login(client, "foldmulti@example.com")

    fa = await client.post("/api/folders", json={"name": "A"}, headers=h)
    assert fa.status_code == 201, fa.text
    a_id = fa.json()["id"]
    fb = await client.post("/api/folders", json={"name": "B"}, headers=h)
    assert fb.status_code == 201, fb.text
    b_id = fb.json()["id"]

    n1 = await client.post(
        "/api/notes",
        json={"title": "In A", "content_json": "{}", "folder_id": a_id},
        headers=h,
    )
    assert n1.status_code == 201, n1.text
    n1_id = n1.json()["id"]
    n2 = await client.post(
        "/api/notes",
        json={"title": "In B", "content_json": "{}", "folder_id": b_id},
        headers=h,
    )
    assert n2.status_code == 201, n2.text
    n2_id = n2.json()["id"]

    both = await client.get(
        "/api/notes",
        params=[("folder_id", a_id), ("folder_id", b_id)],
        headers=h,
    )
    assert both.status_code == 200, both.text
    got = {n["id"] for n in both.json()}
    assert got == {n1_id, n2_id}
