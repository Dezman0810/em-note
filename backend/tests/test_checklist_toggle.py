import json

import pytest

from app.services.checklist_toggle import ChecklistConflict, apply_checklist_toggle


def _item(text: str, checked: bool = False) -> dict:
    return {
        "type": "taskItem",
        "attrs": {"checked": checked},
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _doc(*children: dict) -> str:
    return json.dumps({"type": "doc", "content": list(children)}, ensure_ascii=False)


def _checks(content_json: str) -> list[bool]:
    out: list[bool] = []

    def walk(n: object) -> None:
        if isinstance(n, dict):
            if n.get("type") == "taskItem":
                out.append(bool(n["attrs"]["checked"]))
            for c in n.get("content") or []:
                walk(c)

    walk(json.loads(content_json))
    return out


def test_toggles_only_the_requested_item() -> None:
    src = _doc(
        {"type": "paragraph", "content": [{"type": "text", "text": "Покупки"}]},
        {"type": "taskList", "content": [_item("молоко"), _item("хлеб"), _item("сыр")]},
    )
    out = apply_checklist_toggle(src, 1, True, "хлеб")
    assert out is not None
    assert _checks(out) == [False, True, False]
    # Кроме галочки документ не меняется.
    a, b = json.loads(src), json.loads(out)
    b["content"][1]["content"][1]["attrs"]["checked"] = False
    assert a == b


def test_counts_items_across_lists_in_document_order() -> None:
    src = _doc(
        {"type": "taskList", "content": [_item("a")]},
        {"type": "paragraph"},
        {"type": "taskList", "content": [_item("b", True), _item("c")]},
    )
    out = apply_checklist_toggle(src, 1, False, "b")
    assert out is not None
    assert _checks(out) == [False, False, False]


def test_same_state_is_noop() -> None:
    src = _doc({"type": "taskList", "content": [_item("a", True)]})
    assert apply_checklist_toggle(src, 0, True, "a") is None


def test_changed_text_is_conflict() -> None:
    src = _doc({"type": "taskList", "content": [_item("новый текст")]})
    with pytest.raises(ChecklistConflict):
        apply_checklist_toggle(src, 0, True, "старый текст")


def test_missing_index_is_conflict() -> None:
    src = _doc({"type": "taskList", "content": [_item("a")]})
    with pytest.raises(ChecklistConflict):
        apply_checklist_toggle(src, 5, True, "a")


def test_broken_json_is_conflict() -> None:
    with pytest.raises(ChecklistConflict):
        apply_checklist_toggle("{not json", 0, True, "a")
