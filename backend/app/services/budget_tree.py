from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import BudgetCategory, BudgetLabel


async def all_categories_by_kind(db: AsyncSession, kind: str) -> dict[int, BudgetCategory]:
    rows = (await db.scalars(select(BudgetCategory).where(BudgetCategory.kind == kind))).all()
    return {c.id: c for c in rows}


def category_root_name(category_id: int | None, by_id: dict[int, BudgetCategory]) -> str | None:
    if category_id is None or category_id not in by_id:
        return None
    cur: BudgetCategory | None = by_id.get(category_id)
    seen: set[int] = set()
    root: BudgetCategory | None = cur
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        root = cur
        pid = cur.parent_id
        cur = by_id.get(pid) if pid is not None else None
    return root.name if root else None


def category_path(category_id: int | None, by_id: dict[int, BudgetCategory]) -> str | None:
    if category_id is None or category_id not in by_id:
        return None
    parts: list[str] = []
    cur: BudgetCategory | None = by_id.get(category_id)
    seen: set[int] = set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        parts.append(cur.name)
        pid = cur.parent_id
        cur = by_id.get(pid) if pid is not None else None
    return " / ".join(reversed(parts))


def category_tree(by_id: dict[int, BudgetCategory]) -> list[dict]:
    nodes: dict[int, dict] = {
        c.id: {"id": c.id, "parent_id": c.parent_id, "name": c.name, "children": []}
        for c in by_id.values()
    }
    roots: list[dict] = []
    for c in by_id.values():
        node = nodes[c.id]
        pid = c.parent_id
        if pid is not None and pid in nodes:
            nodes[pid]["children"].append(node)
        else:
            roots.append(node)

    def sort_rec(n: dict) -> None:
        n["children"].sort(key=lambda x: x["name"].lower())
        for ch in n["children"]:
            sort_rec(ch)

    roots.sort(key=lambda x: x["name"].lower())
    for r in roots:
        sort_rec(r)
    return roots


def flat_options_for_select(by_id: dict[int, BudgetCategory]) -> list[dict]:
    tree = category_tree(by_id)
    out: list[dict] = []

    def walk(nodes: list[dict], depth: int, prefix_parts: list[str]) -> None:
        for n in nodes:
            chain = prefix_parts + [n["name"]]
            path_str = " / ".join(chain)
            label = ("— " * depth + n["name"]) if depth else n["name"]
            out.append({"id": n["id"], "depth": depth, "label": label, "path": path_str})
            walk(n["children"], depth + 1, chain)

    walk(tree, 0, [])
    return out


async def all_labels_by_kind(db: AsyncSession, kind: str) -> dict[int, BudgetLabel]:
    rows = (await db.scalars(select(BudgetLabel).where(BudgetLabel.kind == kind))).all()
    return {lb.id: lb for lb in rows}


def label_path(label_id: int | None, by_id: dict[int, BudgetLabel]) -> str | None:
    if label_id is None or label_id not in by_id:
        return None
    parts: list[str] = []
    cur: BudgetLabel | None = by_id.get(label_id)
    seen: set[int] = set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        parts.append(cur.name)
        pid = cur.parent_id
        cur = by_id.get(pid) if pid is not None else None
    return " / ".join(reversed(parts))


def descendant_label_ids(label_id: int, by_kind: dict[int, BudgetLabel]) -> set[int]:
    children_map: dict[int, list[int]] = {}
    for lb in by_kind.values():
        p = lb.parent_id
        if p is None:
            continue
        children_map.setdefault(p, []).append(lb.id)
    out: set[int] = set()
    stack = list(children_map.get(label_id, []))
    while stack:
        lid = stack.pop()
        if lid in out:
            continue
        out.add(lid)
        stack.extend(children_map.get(lid, []))
    return out


def label_tree(by_id: dict[int, BudgetLabel]) -> list[dict]:
    nodes: dict[int, dict] = {
        lb.id: {"id": lb.id, "parent_id": lb.parent_id, "name": lb.name, "children": []}
        for lb in by_id.values()
    }
    roots: list[dict] = []
    for lb in by_id.values():
        node = nodes[lb.id]
        pid = lb.parent_id
        if pid is not None and pid in nodes:
            nodes[pid]["children"].append(node)
        else:
            roots.append(node)

    def sort_rec(n: dict) -> None:
        n["children"].sort(key=lambda x: x["name"].lower())
        for ch in n["children"]:
            sort_rec(ch)

    roots.sort(key=lambda x: x["name"].lower())
    for r in roots:
        sort_rec(r)
    return roots


def flat_label_options(by_id: dict[int, BudgetLabel]) -> list[dict]:
    tree = label_tree(by_id)
    out: list[dict] = []

    def walk(nodes: list[dict], depth: int, prefix_parts: list[str]) -> None:
        for n in nodes:
            chain = prefix_parts + [n["name"]]
            path_str = " / ".join(chain)
            label = ("— " * depth + n["name"]) if depth else n["name"]
            out.append({"id": n["id"], "depth": depth, "label": label, "path": path_str})
            walk(n["children"], depth + 1, chain)

    walk(tree, 0, [])
    return out
