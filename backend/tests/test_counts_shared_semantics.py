"""Счётчики папок и меток на шеренных заметках: личное размещение и личные метки.

Фиксирует числа, которые отдают /api/folders/note-counts и /api/tags/counts,
включая тонкие места: у получателя шаринга своя папка и свои личные метки,
у владельца — канонические.
"""

from httpx import AsyncClient

SHARED_ACCESS_EMAIL_LABEL = "Доступ по email"


async def _register_and_login(client: AsyncClient, email: str) -> tuple[dict[str, str], str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password99", "display_name": "U"},
    )
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]
    r = await client.post("/api/auth/login", json={"email": email, "password": "password99"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, user_id


async def _folder(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    r = await client.post("/api/folders", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _note(
    client: AsyncClient, headers: dict[str, str], title: str, folder_id: str | None = None
) -> str:
    payload: dict[str, object] = {"title": title, "content_json": "{}"}
    if folder_id is not None:
        payload["folder_id"] = folder_id
    r = await client.post("/api/notes", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _tag(
    client: AsyncClient, headers: dict[str, str], name: str, parent_id: str | None = None
) -> str:
    payload: dict[str, object] = {"name": name}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    r = await client.post("/api/tags", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _tag_counts(client: AsyncClient, headers: dict[str, str], **params: str) -> dict[str, int]:
    r = await client.get("/api/tags/counts", params=params or None, headers=headers)
    assert r.status_code == 200, r.text
    return {str(row["tag_id"]): int(row["count"]) for row in r.json()}


async def test_folder_counts_owner_and_recipient_placements(client: AsyncClient) -> None:
    h_owner, _ = await _register_and_login(client, "tagtest@example.com")
    h_bee, bee_id = await _register_and_login(client, "foldercountbee@example.com")

    work = await _folder(client, h_owner, "Work")
    await _note(client, h_owner, "in work", work)
    await _note(client, h_owner, "no folder")
    shared_id = await _note(client, h_owner, "shared out", work)

    sh = await client.post(
        f"/api/notes/{shared_id}/shares",
        headers=h_owner,
        json={"shared_with_user_id": bee_id, "role": "viewer"},
    )
    assert sh.status_code == 201, sh.text

    owner_counts = await client.get("/api/folders/note-counts", headers=h_owner)
    assert owner_counts.status_code == 200, owner_counts.text
    body = owner_counts.json()
    assert body["total"] == 3
    assert body["unfoldered"] == 1
    assert body["folder_counts"] == [{"folder_id": work, "count": 2}]

    # У получателя заметка пока «без папки»: личного размещения нет.
    bee_box = await _folder(client, h_bee, "Inbox")
    before = await client.get("/api/folders/note-counts", headers=h_bee)
    assert before.status_code == 200, before.text
    assert before.json() == {
        "total": 1,
        "unfoldered": 1,
        "folder_counts": [{"folder_id": bee_box, "count": 0}],
    }

    moved = await client.patch(
        f"/api/notes/{shared_id}", headers=h_bee, json={"folder_id": bee_box}
    )
    assert moved.status_code == 200, moved.text

    after = await client.get("/api/folders/note-counts", headers=h_bee)
    assert after.status_code == 200, after.text
    assert after.json() == {
        "total": 1,
        "unfoldered": 0,
        "folder_counts": [{"folder_id": bee_box, "count": 1}],
    }

    # Владельца личное размещение получателя не касается.
    owner_after = await client.get("/api/folders/note-counts", headers=h_owner)
    assert owner_after.json()["folder_counts"] == [{"folder_id": work, "count": 2}]
    assert owner_after.json()["unfoldered"] == 1


async def test_tag_counts_mix_canonical_and_personal_subtree(client: AsyncClient) -> None:
    h_owner, _ = await _register_and_login(client, "tagtest@example.com")
    h_bee, bee_id = await _register_and_login(client, "tagcountbee@example.com")

    own_note = await _note(client, h_owner, "own tagged")
    shared_id = await _note(client, h_owner, "shared tagged")
    root = await _tag(client, h_owner, "Root")
    leaf = await _tag(client, h_owner, "Leaf", parent_id=root)
    for nid in (own_note, shared_id):
        r = await client.post(f"/api/notes/{nid}/tags/{leaf}", headers=h_owner)
        assert r.status_code == 200, r.text

    sh = await client.post(
        f"/api/notes/{shared_id}/shares",
        headers=h_owner,
        json={"shared_with_user_id": bee_id, "role": "viewer"},
    )
    assert sh.status_code == 201, sh.text

    owner_counts = await _tag_counts(client, h_owner)
    assert owner_counts[root] == 2
    assert owner_counts[leaf] == 2

    # Метки владельца получателю не видны; у него своя «Доступ по email» на одну заметку.
    bee_tags = await client.get("/api/tags", headers=h_bee)
    assert bee_tags.status_code == 200, bee_tags.text
    bee_by_name = {t["name"]: t["id"] for t in bee_tags.json()}
    assert set(bee_by_name) == {SHARED_ACCESS_EMAIL_LABEL}
    access_tag = bee_by_name[SHARED_ACCESS_EMAIL_LABEL]
    assert await _tag_counts(client, h_bee) == {access_tag: 1}

    # Личная метка получателя в поддереве: родитель считает ту же заметку один раз.
    bee_root = await _tag(client, h_bee, "BeeRoot")
    bee_leaf = await _tag(client, h_bee, "BeeLeaf", parent_id=bee_root)
    att = await client.post(f"/api/notes/{shared_id}/tags/{bee_leaf}", headers=h_bee)
    assert att.status_code == 200, att.text

    bee_counts = await _tag_counts(client, h_bee)
    assert bee_counts[bee_leaf] == 1
    assert bee_counts[bee_root] == 1
    assert bee_counts[access_tag] == 1


async def test_tag_counts_scoped_by_folder_and_unfoldered(client: AsyncClient) -> None:
    h, _ = await _register_and_login(client, "tagtest@example.com")
    box = await _folder(client, h, "Box")
    tag = await _tag(client, h, "Scoped")

    in_box = await _note(client, h, "boxed", box)
    loose = await _note(client, h, "loose")
    for nid in (in_box, loose):
        r = await client.post(f"/api/notes/{nid}/tags/{tag}", headers=h)
        assert r.status_code == 200, r.text

    assert (await _tag_counts(client, h))[tag] == 2
    assert (await _tag_counts(client, h, folder_id=box))[tag] == 1
    assert (await _tag_counts(client, h, unfoldered="true"))[tag] == 1
    assert (await _tag_counts(client, h, exclude_folder_id=box))[tag] == 1


async def test_tag_counts_unknown_folder_is_404(client: AsyncClient) -> None:
    h, _ = await _register_and_login(client, "tagtest@example.com")
    missing = "00000000-0000-0000-0000-000000000001"
    r = await client.get("/api/tags/counts", params={"folder_id": missing}, headers=h)
    assert r.status_code == 404, r.text
    r2 = await client.get(
        "/api/tags/counts", params={"exclude_folder_id": missing}, headers=h
    )
    assert r2.status_code == 404, r2.text
