import json
import re
import unicodedata


def slugify(name: str, max_len: int = 160) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[-\s]+", "-", s).strip("-")
    return (s[:max_len] if s else "tag") or "tag"


def plain_text_from_tiptap_json(content_json: str) -> str:
    """Best-effort plain text from TipTap/ProseMirror JSON for search indexing."""
    try:
        doc = json.loads(content_json)
    except (json.JSONDecodeError, TypeError):
        return ""
    parts: list[str] = []

    def walk(node: object) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "text" and isinstance(node.get("text"), str):
            parts.append(node["text"])
        for child in node.get("content") or []:
            walk(child)

    walk(doc)
    return " ".join(parts).strip()
