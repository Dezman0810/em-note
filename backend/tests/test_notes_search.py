"""Контракт GET /api/notes/search: слово, часть слова, регистр, кириллица, изоляция."""

from httpx import AsyncClient


async def _auth(client: AsyncClient, email: str) -> dict[str, str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password99", "display_name": "S"},
    )
    assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json={"email": email, "password": "password99"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _note(
    client: AsyncClient, headers: dict[str, str], title: str, plain: str = ""
) -> str:
    r = await client.post(
        "/api/notes",
        json={"title": title, "content_json": "{}", "content_plain": plain},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _search(client: AsyncClient, headers: dict[str, str], q: str, **params: str) -> set[str]:
    r = await client.get("/api/notes/search", params={"q": q, **params}, headers=headers)
    assert r.status_code == 200, r.text
    return {row["id"] for row in r.json()}


async def test_search_matches_whole_word_in_title_and_body(client: AsyncClient) -> None:
    h = await _auth(client, "searchword@example.com")
    in_title = await _note(client, h, "Привычка бегать")
    in_body = await _note(client, h, "Без темы", "тут написано про привычку и кофе")
    other = await _note(client, h, "Совсем другое", "ничего похожего")

    assert await _search(client, h, "привычка") == {in_title}
    assert await _search(client, h, "кофе") == {in_body}
    assert other not in await _search(client, h, "привычка")


async def test_search_is_case_insensitive_including_cyrillic(client: AsyncClient) -> None:
    h = await _auth(client, "searchcase@example.com")
    cyr = await _note(client, h, "Привычка", "Утренний Кофе")
    lat = await _note(client, h, "Morning Routine", "Drink Water")

    assert await _search(client, h, "ПРИВЫЧКА") == {cyr}
    assert await _search(client, h, "привычка") == {cyr}
    assert await _search(client, h, "кОфЕ") == {cyr}
    assert await _search(client, h, "ROUTINE") == {lat}
    assert await _search(client, h, "water") == {lat}


async def test_search_matches_word_prefix(client: AsyncClient) -> None:
    """Пользователь набирает «прив» и ждёт «привычка» — и в заголовке, и в тексте."""
    h = await _auth(client, "searchprefix@example.com")
    in_title = await _note(client, h, "Привычка вставать рано")
    in_body = await _note(client, h, "Дневник", "новая привычка на месяц")

    found = await _search(client, h, "прив")
    assert in_title in found
    assert in_body in found

    assert in_title in await _search(client, h, "Прив")
    assert await _search(client, h, "вста") == {in_title}


async def test_search_short_query_does_not_match_proekty(client: AsyncClient) -> None:
    """«ест» ≠ «ект»: заголовок «Проекты» без этих букв подряд не должен находиться."""
    h = await _auth(client, "searchproekt@example.com")
    projects = await _note(client, h, "Проекты", "план работ по проекту")
    has_est = await _note(client, h, "Другое", "есть задача на завтра")

    found = await _search(client, h, "ест")
    assert projects not in found
    assert has_est in found


async def test_search_matches_substring_inside_title(client: AsyncClient) -> None:
    """Часть слова не с начала: заголовок ищется по подстроке."""
    h = await _auth(client, "searchinfix@example.com")
    nid = await _note(client, h, "Гиперболоид")
    assert nid in await _search(client, h, "болоид")


async def test_search_multiple_words(client: AsyncClient) -> None:
    h = await _auth(client, "searchmulti@example.com")
    both = await _note(client, h, "Отчёт за март", "квартальные цифры готовы")
    only_one = await _note(client, h, "Отчёт за апрель", "ещё не начат")

    found = await _search(client, h, "отчёт за март")
    assert both in found
    assert only_one not in found


async def test_search_ignores_trashed_and_other_users_notes(client: AsyncClient) -> None:
    h_a = await _auth(client, "searchmine@example.com")
    h_b = await _auth(client, "searchtheirs@example.com")
    mine = await _note(client, h_a, "Уникальноеслово alpha")
    trashed = await _note(client, h_a, "Уникальноеслово trashed")
    theirs = await _note(client, h_b, "Уникальноеслово beta")

    assert (await client.delete(f"/api/notes/{trashed}", headers=h_a)).status_code == 204

    assert await _search(client, h_a, "уникальноеслово") == {mine}
    assert await _search(client, h_b, "уникальноеслово") == {theirs}


async def test_search_respects_folder_and_tag_filters(client: AsyncClient) -> None:
    h = await _auth(client, "searchfilters@example.com")
    box = await client.post("/api/folders", json={"name": "Box"}, headers=h)
    assert box.status_code == 201, box.text
    box_id = box.json()["id"]
    tag = await client.post("/api/tags", json={"name": "Mark"}, headers=h)
    assert tag.status_code == 201, tag.text
    tag_id = tag.json()["id"]

    boxed = await client.post(
        "/api/notes",
        json={"title": "заголовок общий", "content_json": "{}", "folder_id": box_id},
        headers=h,
    )
    assert boxed.status_code == 201, boxed.text
    boxed_id = boxed.json()["id"]
    loose_id = await _note(client, h, "заголовок общий тоже")
    assert (
        await client.post(f"/api/notes/{boxed_id}/tags/{tag_id}", headers=h)
    ).status_code == 200

    assert await _search(client, h, "заголовок") == {boxed_id, loose_id}
    assert await _search(client, h, "заголовок", folder_id=box_id) == {boxed_id}
    assert await _search(client, h, "заголовок", unfoldered="true") == {loose_id}
    assert await _search(client, h, "заголовок", tag_id=tag_id) == {boxed_id}
    assert await _search(client, h, "заголовок", exclude_folder_id=box_id) == {loose_id}


async def test_search_reflects_edited_title_and_body(client: AsyncClient) -> None:
    """search_vector — generated-колонка: после PATCH заметка находится по новым словам."""
    h = await _auth(client, "searchedited@example.com")
    nid = await _note(client, h, "Первый заголовок", "первое тело")

    assert await _search(client, h, "второе") == set()

    patched = await client.patch(
        f"/api/notes/{nid}",
        json={"title": "Второй заголовок", "content_plain": "второе тело"},
        headers=h,
    )
    assert patched.status_code == 200, patched.text

    assert await _search(client, h, "второе") == {nid}
    assert await _search(client, h, "второй") == {nid}
    assert await _search(client, h, "первое") == set()


async def test_search_result_is_compact_like_list(client: AsyncClient) -> None:
    h = await _auth(client, "searchcompact@example.com")
    r = await client.post(
        "/api/notes",
        json={
            "title": "Компактный",
            "content_json": '{"type":"doc","content":[' + '{"x":1},' * 200 + '{"x":2}]}',
            "content_plain": "тело заметки",
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    found = await client.get(
        "/api/notes/search", params={"q": "компактный"}, headers=h
    )
    assert found.status_code == 200, found.text
    rows = found.json()
    assert len(rows) == 1
    assert rows[0]["content_json"] == "{}"
    assert rows[0]["content_plain"] == "тело заметки"
    assert rows[0]["my_access"] == "owner"
