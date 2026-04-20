"""Сравнение JSON-документов без учёта форматирования строки."""

import json


def json_doc_equal(a: str, b: str) -> bool:
    if a == b:
        return True
    try:
        return json.loads(a) == json.loads(b)
    except (json.JSONDecodeError, TypeError):
        return False
