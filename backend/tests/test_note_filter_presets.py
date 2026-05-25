"""API сохранённых наборов фильтров заметок."""

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


async def test_note_filter_preset_crud(client: AsyncClient) -> None:
    h = await _register_and_login(client, "presets@example.com")

    nf = await client.post("/api/folders", json={"name": "Work"}, headers=h)
    assert nf.status_code == 201, nf.text
    folder_id = nf.json()["id"]

    r0 = await client.get("/api/note-filter-presets", headers=h)
    assert r0.status_code == 200, r0.text
    assert r0.json() == []

    r1 = await client.post(
        "/api/note-filter-presets",
        json={
            "name": "Задачи",
            "search_query": "дело",
            "folder_ids": [folder_id],
            "exclude_folder_ids": [],
            "tag_ids": [],
            "exclude_tag_ids": [],
            "exclude_tag_undo_ids": [],
        },
        headers=h,
    )
    assert r1.status_code == 201, r1.text
    p = r1.json()
    preset_id = p["id"]
    assert p["name"] == "Задачи"
    assert p["search_query"] == "дело"
    assert p["folder_ids"] == [folder_id]
    assert p["tag_match_all"] is False
    assert p["conjunct_tag_ids"] == []
    assert p["tag_nav_collapsed_ids"] == []

    tag = await client.post("/api/tags", json={"name": "Cj"}, headers=h)
    assert tag.status_code == 201, tag.text
    tag_id = tag.json()["id"]

    r1b = await client.patch(
        f"/api/note-filter-presets/{preset_id}",
        json={"conjunct_tag_ids": [tag_id]},
        headers=h,
    )
    assert r1b.status_code == 200, r1b.text
    assert r1b.json()["conjunct_tag_ids"] == [tag_id]

    r_nav = await client.patch(
        f"/api/note-filter-presets/{preset_id}",
        json={"tag_nav_collapsed_ids": [tag_id]},
        headers=h,
    )
    assert r_nav.status_code == 200, r_nav.text
    assert r_nav.json()["tag_nav_collapsed_ids"] == [tag_id]

    r2 = await client.get("/api/note-filter-presets", headers=h)
    assert len(r2.json()) == 1

    r3 = await client.patch(
        f"/api/note-filter-presets/{preset_id}",
        json={
            "name": "Задачи (пр.)",
            "search_query": None,
            "folder_ids": [],
        },
        headers=h,
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["name"] == "Задачи (пр.)"
    assert r3.json()["search_query"] is None
    assert r3.json()["folder_ids"] == []

    r4 = await client.delete(f"/api/note-filter-presets/{preset_id}", headers=h)
    assert r4.status_code == 204, r4.text
    r5 = await client.get("/api/note-filter-presets", headers=h)
    assert r5.json() == []
