"""Уникальность имён меток среди всех меток пользователя."""

import uuid

from httpx import AsyncClient


async def _headers(client: AsyncClient) -> dict[str, str]:
    email = f"uniqtag_{uuid.uuid4().hex[:12]}@example.com"
    r = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "password99",
            "display_name": "Uniq",
        },
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        "/api/auth/login",
        json={"email": email, "password": "password99"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_duplicate_root_tag_name_conflict(client: AsyncClient) -> None:
    h = await _headers(client)
    a = await client.post("/api/tags", json={"name": "Alpha"}, headers=h)
    assert a.status_code == 201, a.text
    b = await client.post("/api/tags", json={"name": "Alpha"}, headers=h)
    assert b.status_code == 409, b.text
    c = await client.post("/api/tags", json={"name": "alpha"}, headers=h)
    assert c.status_code == 409, c.text


async def test_duplicate_under_same_parent_conflict(client: AsyncClient) -> None:
    h = await _headers(client)
    root = await client.post("/api/tags", json={"name": "R"}, headers=h)
    assert root.status_code == 201, root.text
    rid = root.json()["id"]
    x = await client.post("/api/tags", json={"name": "Kid", "parent_id": rid}, headers=h)
    assert x.status_code == 201, x.text
    y = await client.post("/api/tags", json={"name": "Kid", "parent_id": rid}, headers=h)
    assert y.status_code == 409, y.text


async def test_same_name_different_parents_conflict(client: AsyncClient) -> None:
    h = await _headers(client)
    r1 = await client.post("/api/tags", json={"name": "A"}, headers=h)
    r2 = await client.post("/api/tags", json={"name": "B"}, headers=h)
    assert r1.status_code == 201 and r2.status_code == 201
    id1, id2 = r1.json()["id"], r2.json()["id"]
    c1 = await client.post("/api/tags", json={"name": "Same", "parent_id": id1}, headers=h)
    assert c1.status_code == 201, c1.text
    c2 = await client.post("/api/tags", json={"name": "Same", "parent_id": id2}, headers=h)
    assert c2.status_code == 409, c2.text
