import re
from datetime import date, timedelta
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import and_, case, extract, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.api.deps import get_db, require_budget_access
from app.models.budget import (
    BudgetCategory,
    BudgetCommentCategoryRule,
    BudgetCommentLabelRule,
    BudgetLabel,
    BudgetTemplate,
    BudgetTransaction,
    budget_transaction_labels,
)
from app.models.user import User
from app.schemas.budget import (
    CategoryCreate,
    CategoryOut,
    CategoryPatch,
    CommentLabelRuleCreate,
    CommentLabelRuleOut,
    CommentLabelRulePatch,
    CommentRuleCreate,
    CommentRuleOut,
    CommentRulePatch,
    FromTemplateBody,
    LabelCreate,
    LabelOut,
    LabelPatch,
    StatsCategory,
    StatsDaily,
    StatsTotals,
    TemplateCreate,
    TemplateOut,
    TemplatePatch,
    TransactionCreate,
    TransactionOut,
    TransactionPatch,
)
from app.services.budget_tree import (
    all_categories_by_kind,
    all_labels_by_kind,
    category_path,
    category_root_name,
    category_tree,
    descendant_label_ids,
    flat_label_options,
    flat_options_for_select,
    label_path,
    label_tree,
)

router = APIRouter(prefix="/budget", tags=["budget"])


async def serialize_comment_rule(db: AsyncSession, row: BudgetCommentCategoryRule) -> CommentRuleOut:
    cmap = await all_categories_by_kind(db, row.kind)
    return CommentRuleOut(
        id=row.id,
        kind=row.kind,
        title=row.title,
        pattern=row.pattern,
        category_id=row.category_id,
        category_path=category_path(row.category_id, cmap),
        sort_order=row.sort_order,
    )


async def serialize_comment_label_rule(db: AsyncSession, row: BudgetCommentLabelRule) -> CommentLabelRuleOut:
    lab = await db.get(BudgetLabel, row.label_id)
    lmap = await all_labels_by_kind(db, row.kind)
    return CommentLabelRuleOut(
        id=row.id,
        kind=row.kind,
        title=row.title,
        pattern=row.pattern,
        label_id=row.label_id,
        label_name=lab.name if lab else None,
        label_path=label_path(row.label_id, lmap) if row.label_id else None,
        sort_order=row.sort_order,
    )


def validate_regex_pattern(pattern: str) -> None:
    try:
        re.compile(pattern)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Некорректное регулярное выражение: {e}")


async def label_ids_from_comment_rules(db: AsyncSession, kind: str, note: str | None) -> list[int]:
    text = (note or "").strip()
    if not text:
        return []
    k = kind.lower().strip()
    rules = (await db.scalars(
        select(BudgetCommentLabelRule)
        .where(BudgetCommentLabelRule.kind == k)
        .order_by(BudgetCommentLabelRule.sort_order.asc(), BudgetCommentLabelRule.id.asc())
    )).all()
    out: list[int] = []
    seen: set[int] = set()
    for r in rules:
        try:
            if re.search(r.pattern, text, re.IGNORECASE):
                lid = int(r.label_id)
                if lid not in seen:
                    seen.add(lid)
                    out.append(lid)
        except re.error:
            continue
    return out


async def merge_client_and_rule_label_ids(
    db: AsyncSession,
    kind: str,
    note: str | None,
    client_ids: list[int],
    merge_rules: bool,
) -> list[int]:
    ordered: list[int] = list(dict.fromkeys(client_ids))
    if not merge_rules:
        return ordered
    for lid in await label_ids_from_comment_rules(db, kind, note):
        if lid not in ordered:
            ordered.append(lid)
    return ordered


async def serialize_transaction(db: AsyncSession, t: BudgetTransaction) -> TransactionOut:
    cmap = await all_categories_by_kind(db, t.kind)
    cp = category_path(t.category_id, cmap)
    lbl_map = await all_labels_by_kind(db, t.kind)
    labels_sorted = sorted(t.labels, key=lambda L: (L.name.lower(), L.id))
    return TransactionOut(
        id=t.id,
        kind=t.kind,
        amount=t.amount,
        category_id=t.category_id,
        category_path=cp,
        legacy_category=t.legacy_category,
        note=t.note,
        occurred_on=t.occurred_on,
        labels=[
            LabelOut(
                id=L.id,
                kind=L.kind,
                name=L.name,
                parent_id=L.parent_id,
                path=label_path(L.id, lbl_map),
            )
            for L in labels_sorted
        ],
    )


async def serialize_template(db: AsyncSession, tpl: BudgetTemplate) -> TemplateOut:
    cmap = await all_categories_by_kind(db, tpl.kind)
    cp = category_path(tpl.category_id, cmap)
    return TemplateOut(
        id=tpl.id,
        title=tpl.title,
        kind=tpl.kind,
        amount=tpl.amount,
        category_id=tpl.category_id,
        category_path=cp,
        note=tpl.note,
    )


async def ensure_category_matches(db: AsyncSession, kind: str, category_id: int | None):
    if category_id is None:
        return
    cat = await db.get(BudgetCategory, category_id)
    if not cat:
        raise HTTPException(404, "Категория не найдена")
    if cat.kind != kind:
        raise HTTPException(400, "Тип категории не совпадает с типом операции (доход/расход)")


async def ensure_labels_match(db: AsyncSession, kind: str, label_ids: list[int] | None):
    if not label_ids:
        return
    rows = (await db.scalars(select(BudgetLabel).where(BudgetLabel.id.in_(label_ids)))).all()
    if len(rows) != len(set(label_ids)):
        raise HTTPException(
            400,
            "Одна или несколько меток не найдены в базе. Обновите страницу (F5) и выберите метки заново.",
        )
    for lb in rows:
        if lb.kind != kind:
            raise HTTPException(
                400,
                "Метка относится к другому типу (доход/расход), чем операция. Переключите вид операции или метку.",
            )


async def ensure_label_matches(db: AsyncSession, kind: str, label_id: int):
    lb = await db.get(BudgetLabel, label_id)
    if not lb:
        raise HTTPException(404, "Метка не найдена (возможно, удалена). Обновите список меток.")
    if lb.kind != kind:
        raise HTTPException(400, "Метка относится к другому типу (доход/расход)")


async def sync_transaction_labels(db: AsyncSession, row: BudgetTransaction, label_ids: list[int]):
    await db.refresh(row, attribute_names=["labels"])
    if not label_ids:
        row.labels = []
        return
    labs = (await db.scalars(select(BudgetLabel).where(BudgetLabel.id.in_(label_ids)))).all()
    by_id = {x.id: x for x in labs}
    ordered = [by_id[i] for i in label_ids if i in by_id]
    row.labels = ordered


async def assert_label_sibling_name_unique(
    db: AsyncSession,
    kind: str,
    name: str,
    parent_id: int | None,
    exclude_id: int | None,
) -> None:
    stmt = select(BudgetLabel).where(
        BudgetLabel.kind == kind,
        BudgetLabel.name == name,
    )
    stmt = stmt.where(
        BudgetLabel.parent_id.is_(None) if parent_id is None else BudgetLabel.parent_id == parent_id
    )
    if exclude_id is not None:
        stmt = stmt.where(BudgetLabel.id != exclude_id)
    if (await db.scalars(stmt)).first():
        raise HTTPException(400, "Метка с таким именем уже есть в этой группе")


async def ensure_label_parent_matches(db: AsyncSession, kind: str, parent_id: int | None) -> None:
    if parent_id is None:
        return
    p = await db.get(BudgetLabel, parent_id)
    if not p:
        raise HTTPException(
            status_code=400,
            detail="Родительская метка не найдена. Выберите «корень» или обновите список (F5).",
        )
    if p.kind != kind:
        raise HTTPException(400, "Родительская метка другого типа (доход/расход)")


async def serialize_label_out(db: AsyncSession, row: BudgetLabel) -> LabelOut:
    lmap = await all_labels_by_kind(db, row.kind)
    return LabelOut(
        id=row.id,
        kind=row.kind,
        name=row.name,
        parent_id=row.parent_id,
        path=label_path(row.id, lmap),
    )


def descendant_category_ids(cat_id: int, by_kind: dict[int, BudgetCategory]) -> set[int]:
    children_map: dict[int, list[int]] = {}
    for c in by_kind.values():
        p = c.parent_id
        if p is None:
            continue
        children_map.setdefault(p, []).append(c.id)
    out: set[int] = set()
    stack = list(children_map.get(cat_id, []))
    while stack:
        cid = stack.pop()
        if cid in out:
            continue
        out.add(cid)
        stack.extend(children_map.get(cid, []))
    return out


def subtree_category_ids(cat_id: int, by_kind: dict[int, BudgetCategory]) -> set[int]:
    return {cat_id} | descendant_category_ids(cat_id, by_kind)


async def expand_ledger_category_ids(db: AsyncSession, category_ids: list[int]) -> set[int] | None:
    """Выбранные категории + все вложенные. Пустой список -> без фильтра (None)."""
    uniq = sorted({int(x) for x in category_ids if x is not None})
    if not uniq:
        return None
    allowed: set[int] = set()
    for cid in uniq:
        row_c = await db.get(BudgetCategory, cid)
        if row_c:
            allowed |= subtree_category_ids(cid, await all_categories_by_kind(db, row_c.kind))
    return allowed


async def expand_ledger_label_ids(db: AsyncSession, label_ids: list[int]) -> set[int] | None:
    """Выбранные метки и все их потомки. Пустой список в запросе → без фильтра (None)."""
    uniq = sorted({int(x) for x in label_ids if x is not None})
    if not uniq:
        return None
    allowed: set[int] = set()
    for lid in uniq:
        row_lb = await db.get(BudgetLabel, lid)
        if row_lb:
            by_kind = await all_labels_by_kind(db, row_lb.kind)
            allowed |= {lid} | descendant_label_ids(lid, by_kind)
    return allowed


def merge_label_id_query_sources(
    label_ids: list[int] | None,
    txn_lids: str | None,
) -> list[int]:
    """Объединяет повторяющийся query label_ids=1&label_ids=2 и csv txn_lids=1,2,3."""
    out: list[int] = []
    if label_ids:
        for x in label_ids:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
    if txn_lids and txn_lids.strip():
        for chunk in txn_lids.split(","):
            c = chunk.strip()
            if not c:
                continue
            try:
                out.append(int(c))
            except ValueError:
                continue
    return list(dict.fromkeys(out))


async def _transaction_with_labels(db: AsyncSession, txn_id: int) -> BudgetTransaction:
    """После commit коллекция labels надёжно подгружается (m2m + expire_on_commit)."""
    return (await db.scalars(
        select(BudgetTransaction).where(BudgetTransaction.id == txn_id).options(selectinload(BudgetTransaction.labels))
    )).one()


@router.get("/health")
async def health(_user: Annotated[User, Depends(require_budget_access)]):
    return {"status": "ok"}


@router.get("/transactions", response_model=list[TransactionOut])
async def list_transactions(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)],
    from_date: Annotated[
        date | None, Query(description="Inclusive start date (YYYY-MM-DD)")
    ] = None,
    to_date: Annotated[
        date | None, Query(description="Inclusive end date (YYYY-MM-DD)")
    ] = None,
    kind: Annotated[
        str | None, Query(description="Filter by income or expense")
    ] = None,
    category_ids: Annotated[
        list[int] | None,
        Query(description="Filter by category ids (includes subtrees)"),
    ] = None,
    note_q: Annotated[
        str | None, Query(description="Case-insensitive substring in note")
    ] = None,
    label_ids: Annotated[
        list[int] | None,
        Query(description="BudgetTransactions having any of these labels (includes label subtrees)"),
    ] = None,
    txn_lids: Annotated[
        str | None,
        Query(
            description="То же, что label_ids: список id через запятую (надёжнее при прокси); объединяется с label_ids",
        ),
    ] = None,
    sort: Annotated[
        str | None,
        Query(
            description="date_desc|date_asc|amount_desc|amount_asc|kind|category|note",
        ),
    ] = None,
):
    OC = aliased(BudgetCategory)

    stmt = select(BudgetTransaction).options(selectinload(BudgetTransaction.labels))
    if from_date:
        stmt = stmt.where(BudgetTransaction.occurred_on >= from_date)
    if to_date:
        stmt = stmt.where(BudgetTransaction.occurred_on <= to_date)
    if kind:
        k = kind.lower().strip()
        if k not in ("income", "expense"):
            raise HTTPException(400, "kind must be income or expense")
        stmt = stmt.where(BudgetTransaction.kind == k)

    expanded = await expand_ledger_category_ids(db, category_ids or [])
    if expanded is not None:
        if not expanded:
            return []
        stmt = stmt.where(BudgetTransaction.category_id.in_(tuple(sorted(expanded))))

    expanded_lbl = await expand_ledger_label_ids(db, merge_label_id_query_sources(label_ids, txn_lids))
    if expanded_lbl is not None:
        if not expanded_lbl:
            return []
        stmt = stmt.where(
            BudgetTransaction.id.in_(
                select(budget_transaction_labels.c.transaction_id).where(
                    budget_transaction_labels.c.label_id.in_(tuple(sorted(expanded_lbl)))
                )
            )
        )

    # Подстрочное совпадение в SQLite: функция LOWER() не полноценна для кириллицы.
    note_needle: str | None = None
    if note_q and note_q.strip():
        nt = (
            note_q.strip()
            .replace("%", "")
            .replace("_", "")
            .replace('"', "")
            .replace("\\", "")[:260]
        )
        if nt:
            note_needle = nt.lower()

    sort_n = (sort or "date_desc").lower().strip()
    if sort_n == "category":
        stmt = stmt.outerjoin(OC, BudgetTransaction.category_id == OC.id).order_by(
            case((OC.name.is_(None), 1), else_=0),
            OC.name.asc(),
            BudgetTransaction.occurred_on.desc(),
            BudgetTransaction.id.desc(),
        )
    elif sort_n == "note":
        stmt = stmt.order_by(
            case((BudgetTransaction.note.is_(None), 1), else_=0),
            BudgetTransaction.note.asc(),
            BudgetTransaction.occurred_on.desc(),
            BudgetTransaction.id.desc(),
        )
    elif sort_n == "kind":
        stmt = stmt.order_by(
            BudgetTransaction.kind.asc(),
            BudgetTransaction.occurred_on.desc(),
            BudgetTransaction.id.desc(),
        )
    elif sort_n == "amount_asc":
        stmt = stmt.order_by(BudgetTransaction.amount.asc(), BudgetTransaction.id.asc())
    elif sort_n == "amount_desc":
        stmt = stmt.order_by(BudgetTransaction.amount.desc(), BudgetTransaction.id.desc())
    elif sort_n == "date_asc":
        stmt = stmt.order_by(BudgetTransaction.occurred_on.asc(), BudgetTransaction.id.asc())
    else:
        stmt = stmt.order_by(BudgetTransaction.occurred_on.desc(), BudgetTransaction.id.desc())

    rows = list((await db.scalars(stmt)).all())
    if note_needle is not None:
        rows = [
            r
            for r in rows
            if r.note is not None and note_needle in (r.note or "").lower()
        ]
    return [await serialize_transaction(db, t) for t in rows]


@router.post("/transactions", response_model=TransactionOut)
async def create_transaction(db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], body: TransactionCreate):
    await ensure_category_matches(db, body.kind, body.category_id)
    occurred = body.occurred_on or date.today()
    note_val = (body.note or "").strip() or None
    row = BudgetTransaction(
        kind=body.kind,
        amount=body.amount,
        legacy_category=None,
        category_id=body.category_id,
        note=note_val,
        occurred_on=occurred,
    )
    db.add(row)
    await db.flush()
    final_l = await merge_client_and_rule_label_ids(
        db,
        body.kind,
        note_val,
        list(body.label_ids or []),
        body.merge_comment_label_rules,
    )
    await ensure_labels_match(db, body.kind, final_l)
    await sync_transaction_labels(db, row, final_l)
    await db.flush()
    return await serialize_transaction(db, await _transaction_with_labels(db, row.id))


@router.post("/transactions/from-template/{template_id}", response_model=TransactionOut)
async def create_from_template(
    template_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)],
    body: Annotated[FromTemplateBody | None, Body()] = None,
):
    tpl = await db.get(BudgetTemplate, template_id)
    if not tpl:
        raise HTTPException(404, "template not found")
    occurred = date.today()
    if body and body.occurred_on:
        occurred = body.occurred_on
    await ensure_category_matches(db, tpl.kind, tpl.category_id)
    note_val = (tpl.note or "").strip() if tpl.note else None
    row = BudgetTransaction(
        kind=tpl.kind,
        amount=tpl.amount,
        legacy_category=None,
        category_id=tpl.category_id,
        note=note_val,
        occurred_on=occurred,
    )
    db.add(row)
    await db.flush()
    final_l = await merge_client_and_rule_label_ids(db, tpl.kind, note_val, [], True)
    await ensure_labels_match(db, tpl.kind, final_l)
    await sync_transaction_labels(db, row, final_l)
    await db.flush()
    return await serialize_transaction(db, await _transaction_with_labels(db, row.id))


@router.patch("/transactions/{txn_id}", response_model=TransactionOut)
async def patch_transaction(txn_id: int, db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], body: TransactionPatch):
    row = await db.get(BudgetTransaction, txn_id)
    if not row:
        raise HTTPException(404, "transaction not found")
    patch = body.model_dump(exclude_unset=True)
    kind = patch.get("kind", row.kind)
    if "kind" in patch:
        row.kind = kind
    if "amount" in patch and patch["amount"] is not None:
        row.amount = float(patch["amount"])
    if "category_id" in patch:
        row.category_id = patch.get("category_id")
    if "note" in patch:
        n = patch.get("note")
        row.note = (str(n).strip() if n is not None else "") or None
    if "occurred_on" in patch and patch.get("occurred_on") is not None:
        row.occurred_on = patch["occurred_on"]
    await ensure_category_matches(db, row.kind, row.category_id)
    if "label_ids" in patch:
        lids = patch.get("label_ids")
        merge_lr = patch.get("merge_comment_label_rules")
        if merge_lr is None:
            merge_lr = True
        final_l = await merge_client_and_rule_label_ids(
            db, row.kind, row.note, list(lids or []), merge_lr
        )
        await ensure_labels_match(db, row.kind, final_l)
        await sync_transaction_labels(db, row, final_l)
    await db.flush()
    return await serialize_transaction(db, await _transaction_with_labels(db, txn_id))


@router.delete("/transactions/{txn_id}")
async def delete_transaction(txn_id: int, db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)]):
    row = await db.get(BudgetTransaction, txn_id)
    if not row:
        raise HTTPException(404, "transaction not found")
    await db.delete(row)
    await db.flush()
    return {"ok": True}


@router.get("/categories")
async def list_categories_tree(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)],
    kind: str = Query(..., description="income or expense"),
):
    k = kind.lower().strip()
    if k not in ("income", "expense"):
        raise HTTPException(400, "kind must be income or expense")
    by_id = await all_categories_by_kind(db, k)
    return {"tree": category_tree(by_id), "flat": flat_options_for_select(by_id)}


@router.post("/categories", response_model=CategoryOut)
async def create_category(db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], body: CategoryCreate):
    if body.parent_id is not None:
        p = await db.get(BudgetCategory, body.parent_id)
        if not p:
            raise HTTPException(404, "parent category not found")
        if p.kind != body.kind:
            raise HTTPException(400, "parent kind mismatch")
    row = BudgetCategory(kind=body.kind, name=body.name, parent_id=body.parent_id)
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


@router.patch("/categories/{cat_id}", response_model=CategoryOut)
async def patch_category(cat_id: int, db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], body: CategoryPatch):
    row = await db.get(BudgetCategory, cat_id)
    if not row:
        raise HTTPException(404, "category not found")
    patch = body.model_dump(exclude_unset=True)
    if "name" in patch:
        nm = patch.get("name")
        if nm is None or not str(nm).strip():
            raise HTTPException(400, "name invalid")
        row.name = str(nm).strip()
    if "parent_id" in patch:
        pid = patch.get("parent_id")
        if pid is None:
            row.parent_id = None
        else:
            if pid == cat_id:
                raise HTTPException(400, "category cannot be its own parent")
            p = await db.get(BudgetCategory, pid)
            if not p:
                raise HTTPException(404, "parent category not found")
            if p.kind != row.kind:
                raise HTTPException(400, "parent kind mismatch")
            by_kind = await all_categories_by_kind(db, row.kind)
            desc = descendant_category_ids(cat_id, by_kind)
            if pid in desc:
                raise HTTPException(400, "cannot move category under its descendant")
            row.parent_id = pid
    await db.flush()
    await db.refresh(row)
    return row


@router.delete("/categories/{cat_id}")
async def delete_category(cat_id: int, db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)]):
    row = await db.get(BudgetCategory, cat_id)
    if not row:
        raise HTTPException(404, "category not found")
    await db.delete(row)
    await db.flush()
    return {"ok": True}


@router.get("/comment-rules", response_model=list[CommentRuleOut])
async def list_comment_rules(db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], kind: str = Query(..., description="income or expense")):
    k = kind.lower().strip()
    if k not in ("income", "expense"):
        raise HTTPException(400, "kind must be income or expense")
    stmt = (
        select(BudgetCommentCategoryRule)
        .where(BudgetCommentCategoryRule.kind == k)
        .order_by(BudgetCommentCategoryRule.sort_order.asc(), BudgetCommentCategoryRule.id.asc())
    )
    rows = list((await db.scalars(stmt)).all())
    return [await serialize_comment_rule(db, r) for r in rows]


@router.post("/comment-rules", response_model=CommentRuleOut)
async def create_comment_rule(db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], body: CommentRuleCreate):
    validate_regex_pattern(body.pattern)
    await ensure_category_matches(db, body.kind, body.category_id)
    row = BudgetCommentCategoryRule(
        kind=body.kind,
        title=(body.title or "").strip() or None,
        pattern=body.pattern.strip(),
        category_id=body.category_id,
        sort_order=body.sort_order,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return await serialize_comment_rule(db, row)


@router.patch("/comment-rules/{rid}", response_model=CommentRuleOut)
async def patch_comment_rule(rid: int, db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], body: CommentRulePatch):
    row = await db.get(BudgetCommentCategoryRule, rid)
    if not row:
        raise HTTPException(404, "rule not found")
    patch = body.model_dump(exclude_unset=True)
    if "pattern" in patch and patch["pattern"]:
        validate_regex_pattern(str(patch["pattern"]).strip())
        row.pattern = str(patch["pattern"]).strip()
    if "title" in patch:
        t = patch.get("title")
        row.title = (str(t).strip() if t is not None else "") or None
    if "sort_order" in patch and patch["sort_order"] is not None:
        row.sort_order = int(patch["sort_order"])
    if "category_id" in patch and patch["category_id"] is not None:
        row.category_id = int(patch["category_id"])
    await ensure_category_matches(db, row.kind, row.category_id)
    await db.flush()
    await db.refresh(row)
    return await serialize_comment_rule(db, row)


@router.delete("/comment-rules/{rid}")
async def delete_comment_rule(rid: int, db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)]):
    row = await db.get(BudgetCommentCategoryRule, rid)
    if not row:
        raise HTTPException(404, "rule not found")
    await db.delete(row)
    await db.flush()
    return {"ok": True}


@router.get("/labels")
async def list_labels_tree(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)],
    kind: str = Query(..., description="income or expense"),
):
    k = kind.lower().strip()
    if k not in ("income", "expense"):
        raise HTTPException(400, "kind must be income or expense")
    by_id = await all_labels_by_kind(db, k)
    return {"tree": label_tree(by_id), "flat": flat_label_options(by_id)}


@router.post("/labels", response_model=LabelOut)
async def create_label(db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], body: LabelCreate):
    await ensure_label_parent_matches(db, body.kind, body.parent_id)
    nm = body.name.strip()
    await assert_label_sibling_name_unique(db, body.kind, nm, body.parent_id, None)
    row = BudgetLabel(kind=body.kind, name=nm, parent_id=body.parent_id)
    db.add(row)
    try:
        await db.flush()
        await db.refresh(row)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(400, detail="Не удалось сохранить метку (конфликт данных)")
    return await serialize_label_out(db, row)


@router.patch("/labels/{lid}", response_model=LabelOut)
async def patch_label(lid: int, db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], body: LabelPatch):
    row = await db.get(BudgetLabel, lid)
    if not row:
        raise HTTPException(404, "Метка не найдена")
    patch = body.model_dump(exclude_unset=True)
    if "parent_id" in patch:
        pid = patch.get("parent_id")
        if pid is None:
            row.parent_id = None
        else:
            if int(pid) == lid:
                raise HTTPException(400, "Метка не может быть родителем самой себя")
            await ensure_label_parent_matches(db, row.kind, int(pid))
            by_kind = await all_labels_by_kind(db, row.kind)
            desc = descendant_label_ids(lid, by_kind)
            if int(pid) in desc:
                raise HTTPException(400, "Нельзя переместить метку внутрь своей ветки")
            row.parent_id = int(pid)
        if "name" not in patch:
            await assert_label_sibling_name_unique(db, row.kind, row.name, row.parent_id, lid)
    if "name" in patch:
        nm = patch.get("name")
        if nm is None or not str(nm).strip():
            raise HTTPException(400, "Некорректное название")
        row.name = str(nm).strip()
        assert_label_sibling_name_unique(
            db, row.kind, row.name, row.parent_id, lid
        )
    try:
        await db.flush()
        await db.refresh(row)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(400, detail="Не удалось сохранить метку (конфликт данных)")
    return await serialize_label_out(db, row)


@router.delete("/labels/{lid}")
async def delete_label(lid: int, db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)]):
    row = await db.get(BudgetLabel, lid)
    if not row:
        raise HTTPException(404, "Метка не найдена")
    await db.delete(row)
    await db.flush()
    return {"ok": True}


@router.get("/comment-label-rules", response_model=list[CommentLabelRuleOut])
async def list_comment_label_rules(db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], kind: str = Query(..., description="income or expense")):
    k = kind.lower().strip()
    if k not in ("income", "expense"):
        raise HTTPException(400, "kind must be income or expense")
    stmt = (
        select(BudgetCommentLabelRule)
        .where(BudgetCommentLabelRule.kind == k)
        .order_by(BudgetCommentLabelRule.sort_order.asc(), BudgetCommentLabelRule.id.asc())
    )
    rows = list((await db.scalars(stmt)).all())
    return [await serialize_comment_label_rule(db, r) for r in rows]


@router.post("/comment-label-rules", response_model=CommentLabelRuleOut)
async def create_comment_label_rule(db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], body: CommentLabelRuleCreate):
    validate_regex_pattern(body.pattern)
    await ensure_label_matches(db, body.kind, body.label_id)
    row = BudgetCommentLabelRule(
        kind=body.kind,
        title=(body.title or "").strip() or None,
        pattern=body.pattern.strip(),
        label_id=body.label_id,
        sort_order=body.sort_order,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return await serialize_comment_label_rule(db, row)


@router.patch("/comment-label-rules/{rid}", response_model=CommentLabelRuleOut)
async def patch_comment_label_rule(rid: int, db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], body: CommentLabelRulePatch):
    row = await db.get(BudgetCommentLabelRule, rid)
    if not row:
        raise HTTPException(404, "Правило автометки не найдено")
    patch = body.model_dump(exclude_unset=True)
    if "pattern" in patch and patch["pattern"]:
        validate_regex_pattern(str(patch["pattern"]).strip())
        row.pattern = str(patch["pattern"]).strip()
    if "title" in patch:
        t = patch.get("title")
        row.title = (str(t).strip() if t is not None else "") or None
    if "sort_order" in patch and patch["sort_order"] is not None:
        row.sort_order = int(patch["sort_order"])
    if "label_id" in patch and patch["label_id"] is not None:
        row.label_id = int(patch["label_id"])
    await ensure_label_matches(db, row.kind, row.label_id)
    await db.flush()
    await db.refresh(row)
    return await serialize_comment_label_rule(db, row)


@router.delete("/comment-label-rules/{rid}")
async def delete_comment_label_rule(rid: int, db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)]):
    row = await db.get(BudgetCommentLabelRule, rid)
    if not row:
        raise HTTPException(404, "Правило автометки не найдено")
    await db.delete(row)
    await db.flush()
    return {"ok": True}


@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], kind: str | None = None):
    stmt = select(BudgetTemplate).order_by(BudgetTemplate.title)
    if kind:
        k = kind.lower().strip()
        if k not in ("income", "expense"):
            raise HTTPException(400, "kind must be income or expense")
        stmt = stmt.where(BudgetTemplate.kind == k)
    rows = list((await db.scalars(stmt)).all())
    return [await serialize_template(db, t) for t in rows]


@router.post("/templates", response_model=TemplateOut)
async def create_template(db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], body: TemplateCreate):
    await ensure_category_matches(db, body.kind, body.category_id)
    row = BudgetTemplate(
        title=body.title,
        kind=body.kind,
        amount=body.amount,
        category_id=body.category_id,
        note=(body.note or "").strip() or None,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return await serialize_template(db, row)


@router.patch("/templates/{tid}", response_model=TemplateOut)
async def patch_template(tid: int, db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)], body: TemplatePatch):
    row = await db.get(BudgetTemplate, tid)
    if not row:
        raise HTTPException(404, "template not found")
    patch = body.model_dump(exclude_unset=True)
    if "kind" in patch and patch["kind"] is not None:
        k = str(patch["kind"]).lower().strip()
        if k not in ("income", "expense"):
            raise HTTPException(400, "kind must be income or expense")
        row.kind = k
    if "title" in patch and patch["title"] is not None:
        row.title = str(patch["title"]).strip()
    if "amount" in patch and patch["amount"] is not None:
        row.amount = float(patch["amount"])
    if "note" in patch:
        n = patch.get("note")
        row.note = (str(n).strip() if n is not None else "") or None
    if "category_id" in patch:
        row.category_id = patch.get("category_id")
    await ensure_category_matches(db, row.kind, row.category_id)
    await db.flush()
    await db.refresh(row)
    return await serialize_template(db, row)


@router.delete("/templates/{tid}")
async def delete_template(tid: int, db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)]):
    row = await db.get(BudgetTemplate, tid)
    if not row:
        raise HTTPException(404, "template not found")
    await db.delete(row)
    await db.flush()
    return {"ok": True}


@router.get("/export/transactions.xlsx")
async def export_transactions_xlsx(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)],
    from_date: Annotated[
        date | None, Query(description="Inclusive start date (YYYY-MM-DD)")
    ] = None,
    to_date: Annotated[
        date | None, Query(description="Inclusive end date (YYYY-MM-DD)")
    ] = None,
    kind: Annotated[
        str | None, Query(description="Filter by income or expense")
    ] = None,
    category_ids: Annotated[
        list[int] | None,
        Query(description="Filter by category ids (includes subtrees)"),
    ] = None,
    note_q: Annotated[str | None, Query(description="Substring in note")] = None,
    label_ids: Annotated[
        list[int] | None,
        Query(description="Filter by label ids (includes subtrees); OR semantics"),
    ] = None,
    txn_lids: Annotated[
        str | None,
        Query(description="Comma-separated label ids; merged with label_ids"),
    ] = None,
):
    stmt = select(BudgetTransaction).options(selectinload(BudgetTransaction.labels))
    if from_date:
        stmt = stmt.where(BudgetTransaction.occurred_on >= from_date)
    if to_date:
        stmt = stmt.where(BudgetTransaction.occurred_on <= to_date)
    if kind:
        k = kind.lower().strip()
        if k not in ("income", "expense"):
            raise HTTPException(400, "kind must be income or expense")
        stmt = stmt.where(BudgetTransaction.kind == k)

    note_needle: str | None = None
    if note_q and note_q.strip():
        nt_raw = (
            note_q.strip()
            .replace("%", "")
            .replace("_", "")
            .replace('"', "")
            .replace("\\", "")[:260]
        )
        if nt_raw:
            note_needle = nt_raw.lower()

    expanded = await expand_ledger_category_ids(db, category_ids or [])
    expanded_lbl = await expand_ledger_label_ids(db, merge_label_id_query_sources(label_ids, txn_lids))
    if (expanded is not None and not expanded) or (
        expanded_lbl is not None and not expanded_lbl
    ):
        rows = []
    else:
        if expanded is not None:
            stmt = stmt.where(BudgetTransaction.category_id.in_(tuple(sorted(expanded))))
        if expanded_lbl is not None:
            stmt = stmt.where(
                BudgetTransaction.id.in_(
                    select(budget_transaction_labels.c.transaction_id).where(
                        budget_transaction_labels.c.label_id.in_(tuple(sorted(expanded_lbl)))
                    )
                )
            )

        stmt = stmt.order_by(BudgetTransaction.occurred_on.asc(), BudgetTransaction.id.asc())
        rows = list((await db.scalars(stmt)).all())
        if note_needle is not None:
            rows = [
                r
                for r in rows
                if r.note is not None and note_needle in (r.note or "").lower()
            ]

    wb = Workbook(write_only=False)
    ws = wb.active
    ws.title = "Операции"
    ws.append(["Дата", "Тип", "Сумма", "Категория", "Метки", "Комментарий"])
    for t in rows:
        cp = category_path(t.category_id, await all_categories_by_kind(db, t.kind))
        cat_label = cp or t.legacy_category or ""
        type_ru = "доход" if t.kind == "income" else "расход"
        tags = ", ".join(sorted(L.name for L in t.labels)) if t.labels else ""
        ws.append(
            [
                t.occurred_on.isoformat(),
                type_ru,
                round(t.amount, 2),
                cat_label,
                tags,
                t.note or "",
            ]
        )
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    fn = "transactions_export.xlsx"
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/stats/totals-all-time", response_model=StatsTotals)
async def stats_totals_all_time(db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)]):
    """Сумма всех доходов и всех расходов за всё время; баланс = доходы − расходы."""
    ti = (await db.execute(
        select(func.coalesce(func.sum(BudgetTransaction.amount), 0.0)).where(BudgetTransaction.kind == "income")
    )).scalar_one()
    te = (await db.execute(
        select(func.coalesce(func.sum(BudgetTransaction.amount), 0.0)).where(BudgetTransaction.kind == "expense")
    )).scalar_one()
    a = float(ti or 0.0)
    b = float(te or 0.0)
    return StatsTotals(total_income=a, total_expense=b, balance=a - b)


@router.get("/stats/daily", response_model=list[StatsDaily])
async def stats_daily(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)],
    from_date: date = Query(..., description="Start date inclusive"),
    to_date: date = Query(default_factory=date.today, description="End date inclusive"),
    kind_filter: Annotated[
        str | None, Query(alias="kind", description="Optional: income | expense")
    ] = None,
):
    if to_date < from_date:
        raise HTTPException(400, "to_date must be >= from_date")
    if kind_filter:
        k = kind_filter.lower().strip()
        if k not in ("income", "expense"):
            raise HTTPException(400, "kind must be income or expense")
        rows = (await db.execute(
            select(
                BudgetTransaction.occurred_on,
                BudgetTransaction.kind,
                func.coalesce(func.sum(BudgetTransaction.amount), 0.0),
            )
            .where(
                and_(
                    BudgetTransaction.occurred_on >= from_date,
                    BudgetTransaction.occurred_on <= to_date,
                    BudgetTransaction.kind == k,
                )
            )
            .group_by(BudgetTransaction.occurred_on, BudgetTransaction.kind)
            .order_by(BudgetTransaction.occurred_on)
        )).all()
        by_day: dict[date, dict[str, float]] = {}
        for d, kv, total in rows:
            if d not in by_day:
                by_day[d] = {"income": 0.0, "expense": 0.0}
            by_day[d][kv] = float(total)
    else:
        rows = (await db.execute(
            select(
                BudgetTransaction.occurred_on,
                BudgetTransaction.kind,
                func.coalesce(func.sum(BudgetTransaction.amount), 0.0),
            )
            .where(
                and_(
                    BudgetTransaction.occurred_on >= from_date,
                    BudgetTransaction.occurred_on <= to_date,
                )
            )
            .group_by(BudgetTransaction.occurred_on, BudgetTransaction.kind)
            .order_by(BudgetTransaction.occurred_on)
        )).all()
        by_day = {}
        for d, kv, total in rows:
            if d not in by_day:
                by_day[d] = {"income": 0.0, "expense": 0.0}
            by_day[d][kv] = float(total)

    out: list[StatsDaily] = []
    cur = from_date
    while cur <= to_date:
        bucket = by_day.get(cur, {"income": 0.0, "expense": 0.0})
        out.append(
            StatsDaily(
                day=cur,
                income=bucket["income"],
                expense=bucket["expense"],
            )
        )
        cur += timedelta(days=1)
    return out


@router.get("/stats/by-category", response_model=list[StatsCategory])
async def stats_by_category(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)],
    from_date: date = Query(...),
    to_date: date = Query(default_factory=date.today),
    kind: str = Query(..., description="income or expense"),
    level: Annotated[
        str,
        Query(
            description="leaf — полный путь категории; root — группировка по верхнему уровню дерева",
        ),
    ] = "leaf",
):
    if to_date < from_date:
        raise HTTPException(400, "to_date must be >= from_date")
    k = kind.lower().strip()
    if k not in ("income", "expense"):
        raise HTTPException(400, "kind must be income or expense")
    lv = level.lower().strip()
    if lv not in ("leaf", "root"):
        raise HTTPException(400, "level must be leaf or root")

    cmap = await all_categories_by_kind(db, k)
    totals: dict[str, float] = {}

    rows_id = (await db.execute(
        select(BudgetTransaction.category_id, func.coalesce(func.sum(BudgetTransaction.amount), 0.0))
        .where(
            and_(
                BudgetTransaction.occurred_on >= from_date,
                BudgetTransaction.occurred_on <= to_date,
                BudgetTransaction.kind == k,
                BudgetTransaction.category_id.isnot(None),
            )
        )
        .group_by(BudgetTransaction.category_id)
    )).all()

    for cid, total in rows_id:
        if lv == "root":
            rn = category_root_name(int(cid), cmap)
            label = rn or "(категория)"
        else:
            label = category_path(int(cid), cmap) or "(категория)"
        totals[label] = totals.get(label, 0.0) + float(total)

    legacy_expr = func.coalesce(func.nullif(func.trim(BudgetTransaction.legacy_category), ""), "")
    rows_leg = (await db.execute(
        select(legacy_expr, func.coalesce(func.sum(BudgetTransaction.amount), 0.0))
        .where(
            and_(
                BudgetTransaction.occurred_on >= from_date,
                BudgetTransaction.occurred_on <= to_date,
                BudgetTransaction.kind == k,
                BudgetTransaction.category_id.is_(None),
            )
        )
        .group_by(legacy_expr)
    )).all()

    for leg, total in rows_leg:
        key = leg if str(leg).strip() else "(без категории)"
        totals[key] = totals.get(key, 0.0) + float(total)

    ordered = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    return [StatsCategory(category=k, amount=v) for k, v in ordered]


@router.get("/stats/by-month", response_model=list[dict])
async def stats_by_month(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(require_budget_access)],
    from_date: date = Query(...),
    to_date: date = Query(default_factory=date.today),
):
    if to_date < from_date:
        raise HTTPException(400, "to_date must be >= from_date")
    y1, m1 = from_date.year, from_date.month
    y2, m2 = to_date.year, to_date.month

    rows = (await db.execute(
        select(
            extract("year", BudgetTransaction.occurred_on),
            extract("month", BudgetTransaction.occurred_on),
            BudgetTransaction.kind,
            func.coalesce(func.sum(BudgetTransaction.amount), 0.0),
        )
        .where(
            and_(
                BudgetTransaction.occurred_on >= from_date,
                BudgetTransaction.occurred_on <= to_date,
            )
        )
        .group_by(
            extract("year", BudgetTransaction.occurred_on),
            extract("month", BudgetTransaction.occurred_on),
            BudgetTransaction.kind,
        )
    )).all()

    month_map: dict[tuple[int, int], dict[str, float]] = {}
    for year, month, kind_val, total in rows:
        key = (int(year), int(month))
        if key not in month_map:
            month_map[key] = {"income": 0.0, "expense": 0.0}
        month_map[key][kind_val] = float(total)

    out = []
    y, m = y1, m1
    while (y, m) <= (y2, m2):
        bucket = month_map.get((y, m), {"income": 0.0, "expense": 0.0})
        out.append(
            {
                "year": y,
                "month": m,
                "label": f"{y:04d}-{m:02d}",
                "income": bucket["income"],
                "expense": bucket["expense"],
            }
        )
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


