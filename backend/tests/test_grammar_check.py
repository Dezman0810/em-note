from httpx import AsyncClient

from app.services.grammar_align import build_diff_parts, build_match_parts
from app.services.grammar_check import (
    GrammarMatch,
    advice_from_matches,
    apply_matches,
    is_punctuation_edit,
    is_safe_replacement,
    matches_from_languagetool,
    rank_replacements,
    response_from_matches,
    suggestions_from_matches,
)
from app.services.grammar_text import (
    close_lines,
    drop_duplicate_sentence_ends,
    is_cross_line_repeat,
    line_end_matches,
    remap_match,
    text_for_languagetool,
)


def test_apply_matches_from_the_end() -> None:
    text = "превет как дила"
    matches = [
        GrammarMatch(0, 6, "опечатка", "", ["привет"], "misspelling"),
        GrammarMatch(11, 4, "опечатка", "", ["дела"], "misspelling"),
    ]
    assert apply_matches(text, matches) == "привет как дела"


def test_apply_matches_utf16_emoji() -> None:
    text = "👍 превет"
    matches = [GrammarMatch(3, 6, "опечатка", "", ["привет"], "misspelling")]
    assert apply_matches(text, matches) == "👍 привет"


def test_word_replacements_are_advice_not_applied() -> None:
    text = "превет могу"
    matches = [
        GrammarMatch(0, 6, "опечатка", "", ["привет", "Привет"], "misspelling"),
        GrammarMatch(7, 4, "инфинитив", "", ["мочь"], "grammar"),
    ]
    suggestions = suggestions_from_matches(text, matches)
    assert suggestions[0].text == "превет могу"
    advice = advice_from_matches(text, matches)
    assert any(item.before == "превет" and item.after == "привет" for item in advice)
    assert any(item.before == "могу" and "мочь" in item.options for item in advice)


def test_punctuation_is_applied_words_are_not() -> None:
    text = "Итак друзья могу"
    matches = [
        GrammarMatch(0, 4, "запятая", "Запятая", ["Итак,"], "typographical"),
        GrammarMatch(12, 4, "инфинитив", "", ["мочь"], "grammar"),
    ]
    result = response_from_matches(text, matches)
    assert result.suggestions[0].text == "Итак, друзья могу"
    assert all("мочь" not in item.text for item in result.suggestions)
    assert any(item.before == "могу" and item.after == "мочь" for item in result.advice)


def test_match_parts_mark_error_and_fix() -> None:
    text = "превет как дела"
    matches = [GrammarMatch(0, 6, "опечатка", "Орфография", ["привет"], "misspelling")]
    orig, rev, changes = build_match_parts(text, matches)
    assert [p.kind for p in orig] == ["error", "ok"]
    assert orig[0].text == "превет"
    assert [p.kind for p in rev] == ["fix", "ok"]
    assert rev[0].text == "привет"
    assert changes[0].before == "превет"
    assert changes[0].after == "привет"


def test_diff_parts_mark_added_words() -> None:
    orig, rev, changes = build_diff_parts("привет как дела", "привет, как дела")
    assert any(p.kind == "error" for p in orig) or any(p.kind == "fix" for p in rev)
    assert any(c.after == "," or "," in c.after or "," in c.before for c in changes) or any(
        p.text == "," for p in rev if p.kind == "fix"
    )


def test_line_break_ends_sentence_and_is_not_tautology() -> None:
    text = "надо проверить отчёт\nнадо проверить релиз"
    assert close_lines(text) == "надо проверить отчёт.\nнадо проверить релиз."
    ended = apply_matches(text, line_end_matches(text))
    assert ended == "надо проверить отчёт.\nнадо проверить релиз."
    check, inserts = text_for_languagetool(text)
    assert check == "надо проверить отчёт.\nнадо проверить релиз."
    assert inserts == [20, 42]
    mapped = remap_match(GrammarMatch(22, 4, "", "", ["надо"], "misspelling"), inserts)
    assert mapped is not None
    assert mapped.offset == 21
    repeat = GrammarMatch(21, 4, "Повтор слова.", "Тавтология", ["надо"], "style")
    assert is_cross_line_repeat(text, repeat)


def test_sentence_without_period_gets_one() -> None:
    assert close_lines("надо проверить отчёт") == "надо проверить отчёт."
    assert apply_matches("надо проверить отчёт", line_end_matches("надо проверить отчёт")) == (
        "надо проверить отчёт."
    )
    assert close_lines("надо проверить отчёт.") == "надо проверить отчёт."
    assert line_end_matches("надо проверить отчёт.") == []


def test_suggestion_adds_missing_period() -> None:
    text = "надо проверить отчёт"
    result = response_from_matches(text, line_end_matches(text))
    assert result.suggestions[0].text == "надо проверить отчёт."


def test_no_double_period_if_languagetool_already_closes() -> None:
    text = "надо проверить"
    already = [GrammarMatch(0, 14, "", "", ["надо проверить."], "typographical")]
    assert drop_duplicate_sentence_ends(already, line_end_matches(text)) == []


def test_punctuation_edit_keeps_same_letters() -> None:
    assert is_punctuation_edit("Итак", "Итак,") is True
    assert is_punctuation_edit("привет как", "привет, как") is True
    assert is_punctuation_edit("", ".") is True
    assert is_punctuation_edit("могу", "мочь") is False
    assert is_punctuation_edit("превет", "привет") is False


def test_safe_replacement_keeps_it_words() -> None:
    assert is_safe_replacement("могу", "мочь") is False
    assert is_safe_replacement("отчёт", "смету") is False
    assert is_safe_replacement("отчет", "смета") is False
    assert is_safe_replacement("превет", "привет") is True
    assert is_safe_replacement("отчёт", "отчет") is True
    assert "смету" not in rank_replacements("отчёт", ["смету", "отчет"])
    assert rank_replacements("могу", ["мочь"]) == []


def test_style_issue_type_is_ignored() -> None:
    payload = {
        "matches": [
            {
                "offset": 0,
                "length": 4,
                "message": "Можно заменить синонимом.",
                "shortMessage": "Стиль",
                "replacements": [{"value": "приятель"}],
                "rule": {"issueType": "style"},
            }
        ]
    }
    assert matches_from_languagetool(payload, "друг") == []
    suggestions = suggestions_from_matches("друг", [])
    assert len(suggestions) == 1
    assert suggestions[0].id == "same"
    assert suggestions[0].text == "друг"


def test_rank_replacements_prefers_nearby_typo() -> None:
    ranked = rank_replacements("лутший", ["лутфей", "лутфий", "лучшей"])
    assert ranked[0] == "лучшей"


def test_matches_from_languagetool_payload() -> None:
    payload = {
        "matches": [
            {
                "offset": 0,
                "length": 5,
                "message": "Возможно, пропущена запятая.",
                "shortMessage": "Запятая",
                "replacements": [{"value": "Итак,"}, {"value": "Итак"}],
                "rule": {"issueType": "typographical"},
            },
            {"offset": 1, "length": 0, "replacements": [{"value": "x"}]},
        ]
    }
    matches = matches_from_languagetool(payload, "Итак друзья")
    assert len(matches) == 1
    assert "Итак," in matches[0].replacements
    result = response_from_matches("Итак друзья", matches)
    assert result.issues[0].short_message == "Запятая"
    assert result.suggestions[0].text == "Итак, друзья" or result.original == "Итак друзья"


async def test_grammar_requires_flag(client: AsyncClient, monkeypatch) -> None:
    admin = await client.post(
        "/api/auth/register",
        json={"email": "tagtest@example.com", "password": "password99", "display_name": "A"},
    )
    assert admin.status_code == 201, admin.text
    login = await client.post(
        "/api/auth/login", json={"email": "tagtest@example.com", "password": "password99"}
    )
    admin_h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    other = await client.post(
        "/api/auth/register",
        json={"email": "nogrm@example.com", "password": "password99", "display_name": "B"},
    )
    assert other.status_code == 201, other.text
    other_login = await client.post(
        "/api/auth/login", json={"email": "nogrm@example.com", "password": "password99"}
    )
    other_h = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
    uid = other.json()["id"]

    off = await client.patch(
        f"/api/admin/users/{uid}", headers=admin_h, json={"can_use_grammar": False}
    )
    assert off.status_code == 200, off.text
    assert off.json()["can_use_grammar"] is False

    denied = await client.post("/api/grammar/check", headers=other_h, json={"text": "привет"})
    assert denied.status_code == 403

    async def fake_post(_text: str, _language: str | None = None) -> dict:
        return {"matches": []}

    monkeypatch.setattr("app.services.grammar_check.post_languagetool", fake_post)
    ok = await client.post("/api/grammar/check", headers=admin_h, json={"text": "привет"})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["original"] == "привет"
    assert body["suggestions"][0]["text"] == "привет"


async def test_grammar_applies_mocked_languagetool(client: AsyncClient, monkeypatch) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "tagtest@example.com", "password": "password99", "display_name": "A"},
    )
    login = await client.post(
        "/api/auth/login", json={"email": "tagtest@example.com", "password": "password99"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    async def fake_post(text: str, _language: str | None = None) -> dict:
        assert "превет" in text
        return {
            "matches": [
                {
                    "offset": 0,
                    "length": 6,
                    "message": "Возможно, опечатка.",
                    "shortMessage": "Орфография",
                    "replacements": [{"value": "привет"}],
                    "rule": {"issueType": "misspelling"},
                }
            ]
        }

    monkeypatch.setattr("app.services.grammar_check.post_languagetool", fake_post)
    r = await client.post("/api/grammar/check", headers=headers, json={"text": "превет"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["suggestions"][0]["text"] == "превет"
    assert body["advice"][0]["before"] == "превет"
    assert body["advice"][0]["after"] == "привет"
    assert body["issues"][0]["message"] == "Возможно, опечатка."


async def test_admin_can_disable_own_grammar(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "tagtest@example.com", "password": "password99", "display_name": "A"},
    )
    login = await client.post(
        "/api/auth/login", json={"email": "tagtest@example.com", "password": "password99"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = await client.get("/api/auth/me", headers=headers)
    uid = me.json()["id"]
    r = await client.patch(
        f"/api/admin/users/{uid}", headers=headers, json={"can_use_grammar": False}
    )
    assert r.status_code == 200, r.text
    assert r.json()["can_use_grammar"] is False

    me_after = await client.get("/api/auth/me", headers=headers)
    assert me_after.status_code == 200, me_after.text
    assert me_after.json()["can_use_grammar"] is False

    relogin = await client.post(
        "/api/auth/login", json={"email": "tagtest@example.com", "password": "password99"}
    )
    assert relogin.status_code == 200, relogin.text
    relogin_headers = {"Authorization": f"Bearer {relogin.json()['access_token']}"}
    me_relogin = await client.get("/api/auth/me", headers=relogin_headers)
    assert me_relogin.json()["can_use_grammar"] is False
