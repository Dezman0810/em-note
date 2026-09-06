"""API привычек: дни недели, повторения, якорь календаря."""

from httpx import AsyncClient


async def _auth(client: AsyncClient, email: str = "tagtest@example.com") -> dict[str, str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password99", "display_name": "Habits"},
    )
    assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": "password99"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_habit_slots_from_anchor_and_unmarked_are_skips(client: AsyncClient) -> None:
    h = await _auth(client)
    created = await client.post(
        "/api/habits",
        headers=h,
        params={"anchor": "2026-09-07"},
        json={"title": "Стакан воды", "icon": "💧", "weekdays": [1, 2, 3, 4, 5], "target_days": 10},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["target_days"] == 10
    assert len(body["slots"]) == 10
    assert body["slots"][0]["day"] == "2026-09-07"
    assert body["slots"][-1]["day"] == "2026-09-18"
    assert all(s["state"] == "empty" for s in body["slots"])
    hid = body["id"]

    checked = await client.put(
        f"/api/habits/{hid}/day",
        headers=h,
        params={"anchor": "2026-09-07"},
        json={"day": "2026-09-07", "status": "done"},
    )
    assert checked.status_code == 200, checked.text
    got = checked.json()
    assert got["done_count"] == 1
    assert got["missed_count"] == 0
    assert got["slots"][0]["state"] == "done"
    assert got["percent"] == 10


async def test_habit_slots_stay_on_starts_on_when_viewing_later_date(client: AsyncClient) -> None:
    h = await _auth(client)
    created = await client.post(
        "/api/habits",
        headers=h,
        json={
            "title": "Стакан воды",
            "icon": "💧",
            "weekdays": [1, 2, 3, 4, 5],
            "target_days": 10,
            "starts_on": "2026-09-06",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["starts_on"] == "2026-09-06"
    assert created.json()["slots"][0]["day"] == "2026-09-07"
    assert all(s["state"] == "empty" for s in created.json()["slots"])

    later = await client.get("/api/habits", headers=h, params={"anchor": "2026-09-13"})
    assert later.status_code == 200, later.text
    slots = later.json()[0]["slots"]
    days = [s["day"] for s in slots]
    assert "2026-09-07" in days
    assert "2026-09-11" in days
    assert all(s["state"] == "empty" for s in slots if s["day"] < "2026-09-13")

    hid = created.json()["id"]
    moved = await client.patch(
        f"/api/habits/{hid}",
        headers=h,
        json={"starts_on": "2026-09-14"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["starts_on"] == "2026-09-14"
    assert moved.json()["slots"][0]["day"] == "2026-09-14"


async def test_habit_public_link_is_view_only_and_revocable(client: AsyncClient) -> None:
    h = await _auth(client)
    created = await client.post(
        "/api/habits",
        headers=h,
        json={"title": "Стакан воды", "weekdays": [1, 2, 3, 4, 5], "target_days": 10},
    )
    assert created.status_code == 201, created.text

    missing = await client.get("/api/habits/public-link", headers=h)
    assert missing.status_code == 404

    made = await client.put("/api/habits/public-link", headers=h)
    assert made.status_code == 200, made.text
    token = made.json()["token"]
    assert token

    pub = await client.get(f"/api/public/habits/{token}")
    assert pub.status_code == 200, pub.text
    body = pub.json()
    assert body["can_edit"] is False
    assert len(body["habits"]) == 1
    assert body["habits"][0]["title"] == "Стакан воды"

    hid = created.json()["id"]
    denied = await client.put(
        f"/api/habits/{hid}/day",
        json={"day": "2026-09-07", "status": "done"},
    )
    assert denied.status_code == 401

    closed = await client.delete("/api/habits/public-link", headers=h)
    assert closed.status_code == 204
    gone = await client.get(f"/api/public/habits/{token}")
    assert gone.status_code == 404


async def test_habit_day_comment_survives_status_change(client: AsyncClient) -> None:
    h = await _auth(client)
    created = await client.post(
        "/api/habits",
        headers=h,
        json={
            "title": "Стакан воды",
            "weekdays": [1, 2, 3, 4, 5],
            "target_days": 10,
            "starts_on": "2026-09-07",
        },
    )
    assert created.status_code == 201, created.text
    hid = created.json()["id"]
    marked = await client.put(
        f"/api/habits/{hid}/day",
        headers=h,
        json={"day": "2026-09-07", "status": "done", "comment": "два стакана"},
    )
    assert marked.status_code == 200, marked.text
    slot = next(s for s in marked.json()["slots"] if s["day"] == "2026-09-07")
    assert slot["state"] == "done"
    assert slot["comment"] == "два стакана"

    missed = await client.put(
        f"/api/habits/{hid}/day",
        headers=h,
        json={"day": "2026-09-07", "status": "missed"},
    )
    assert missed.status_code == 200, missed.text
    slot = next(s for s in missed.json()["slots"] if s["day"] == "2026-09-07")
    assert slot["state"] == "missed"
    assert slot["comment"] == "два стакана"

    cleared = await client.put(
        f"/api/habits/{hid}/day",
        headers=h,
        json={"day": "2026-09-07", "status": "clear"},
    )
    assert cleared.status_code == 200, cleared.text
    slot = next(s for s in cleared.json()["slots"] if s["day"] == "2026-09-07")
    assert slot["state"] == "empty"
    assert slot["comment"] == "два стакана"

    done_again = await client.put(
        f"/api/habits/{hid}/day",
        headers=h,
        json={"day": "2026-09-07", "status": "done"},
    )
    assert done_again.status_code == 200, done_again.text
    slot = next(s for s in done_again.json()["slots"] if s["day"] == "2026-09-07")
    assert slot["state"] == "done"
    assert slot["comment"] == "два стакана"

    only_note = await client.put(
        f"/api/habits/{hid}/day",
        headers=h,
        json={"day": "2026-09-08", "comment": "просто заметка"},
    )
    assert only_note.status_code == 200, only_note.text
    slot = next(s for s in only_note.json()["slots"] if s["day"] == "2026-09-08")
    assert slot["state"] == "empty"
    assert slot["comment"] == "просто заметка"


async def test_habit_sort_order_1_is_on_top(client: AsyncClient) -> None:
    h = await _auth(client)
    a = await client.post(
        "/api/habits",
        headers=h,
        json={"title": "Первая", "weekdays": [1], "target_days": 5, "starts_on": "2026-09-07"},
    )
    b = await client.post(
        "/api/habits",
        headers=h,
        json={"title": "Вторая", "weekdays": [1], "target_days": 5, "starts_on": "2026-09-07"},
    )
    assert a.status_code == 201 and b.status_code == 201, a.text + b.text
    assert a.json()["sort_order"] == 1
    assert b.json()["sort_order"] == 2
    moved = await client.patch(
        f"/api/habits/{b.json()['id']}",
        headers=h,
        json={"sort_order": 1},
    )
    assert moved.status_code == 200, moved.text
    listed = await client.get("/api/habits", headers=h)
    titles = [row["title"] for row in listed.json()]
    assert titles[0] == "Первая"
    # both can be 1; created_at keeps the older first unless we also bump A
    await client.patch(f"/api/habits/{a.json()['id']}", headers=h, json={"sort_order": 2})
    listed = await client.get("/api/habits", headers=h)
    titles = [row["title"] for row in listed.json()]
    assert titles == ["Вторая", "Первая"]
