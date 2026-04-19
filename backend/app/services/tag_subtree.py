import uuid

from app.models.tag import Tag


def subtree_tag_ids(root_id: uuid.UUID, user_tags: list[Tag]) -> list[uuid.UUID]:
    """Все id меток в поддереве root (включая root). Только связи из user_tags."""
    by_parent: dict[uuid.UUID, list[uuid.UUID]] = {}
    for t in user_tags:
        if t.parent_id is not None:
            by_parent.setdefault(t.parent_id, []).append(t.id)
    out: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    stack = [root_id]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        out.append(cur)
        for ch in by_parent.get(cur, []):
            stack.append(ch)
    return out
