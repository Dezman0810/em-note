"""Shared family budget tables + users.can_use_budget

Revision ID: 202609122200
Revises: 202609122100
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609122200"
down_revision: Union[str, None] = "202609122100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    user_cols = {c["name"] for c in insp.get_columns("users")}
    if "can_use_budget" not in user_cols:
        op.add_column(
            "users",
            sa.Column("can_use_budget", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    tables = set(insp.get_table_names())
    if "budget_categories" not in tables:
        op.create_table(
            "budget_categories",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("kind", sa.String(length=8), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("parent_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["parent_id"], ["budget_categories.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_budget_categories_kind", "budget_categories", ["kind"])
        op.create_index("ix_budget_categories_parent_id", "budget_categories", ["parent_id"])

    if "budget_labels" not in tables:
        op.create_table(
            "budget_labels",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("kind", sa.String(length=8), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("parent_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["parent_id"], ["budget_labels.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_budget_labels_kind", "budget_labels", ["kind"])
        op.create_index("ix_budget_labels_parent_id", "budget_labels", ["parent_id"])

    if "budget_transactions" not in tables:
        op.create_table(
            "budget_transactions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("kind", sa.String(length=8), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("category", sa.String(length=128), nullable=True),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("note", sa.String(length=512), nullable=True),
            sa.Column("occurred_on", sa.Date(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["category_id"], ["budget_categories.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_budget_transactions_occurred_on", "budget_transactions", ["occurred_on"])
        op.create_index("ix_budget_transactions_category_id", "budget_transactions", ["category_id"])

    if "budget_transaction_labels" not in tables:
        op.create_table(
            "budget_transaction_labels",
            sa.Column("transaction_id", sa.Integer(), nullable=False),
            sa.Column("label_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["transaction_id"], ["budget_transactions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["label_id"], ["budget_labels.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("transaction_id", "label_id"),
        )

    if "budget_templates" not in tables:
        op.create_table(
            "budget_templates",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("title", sa.String(length=160), nullable=False),
            sa.Column("kind", sa.String(length=8), nullable=False),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("note", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["category_id"], ["budget_categories.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_budget_templates_kind", "budget_templates", ["kind"])
        op.create_index("ix_budget_templates_category_id", "budget_templates", ["category_id"])

    if "budget_comment_category_rules" not in tables:
        op.create_table(
            "budget_comment_category_rules",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("kind", sa.String(length=8), nullable=False),
            sa.Column("title", sa.String(length=160), nullable=True),
            sa.Column("pattern", sa.String(length=512), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.ForeignKeyConstraint(["category_id"], ["budget_categories.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_budget_comment_category_rules_kind", "budget_comment_category_rules", ["kind"])
        op.create_index(
            "ix_budget_comment_category_rules_category_id",
            "budget_comment_category_rules",
            ["category_id"],
        )

    if "budget_comment_label_rules" not in tables:
        op.create_table(
            "budget_comment_label_rules",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("kind", sa.String(length=8), nullable=False),
            sa.Column("title", sa.String(length=160), nullable=True),
            sa.Column("pattern", sa.String(length=512), nullable=False),
            sa.Column("label_id", sa.Integer(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.ForeignKeyConstraint(["label_id"], ["budget_labels.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_budget_comment_label_rules_kind", "budget_comment_label_rules", ["kind"])
        op.create_index("ix_budget_comment_label_rules_label_id", "budget_comment_label_rules", ["label_id"])

    op.execute(
        sa.text(
            """
            INSERT INTO budget_labels (kind, name, parent_id)
            SELECT 'expense', 'полезно', NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM budget_labels
                WHERE kind = 'expense' AND name = 'полезно' AND parent_id IS NULL
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO budget_labels (kind, name, parent_id)
            SELECT 'expense', 'не полезно', NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM budget_labels
                WHERE kind = 'expense' AND name = 'не полезно' AND parent_id IS NULL
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_table("budget_comment_label_rules")
    op.drop_table("budget_comment_category_rules")
    op.drop_table("budget_templates")
    op.drop_table("budget_transaction_labels")
    op.drop_table("budget_transactions")
    op.drop_table("budget_labels")
    op.drop_table("budget_categories")
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if any(c["name"] == "can_use_budget" for c in insp.get_columns("users")):
        op.drop_column("users", "can_use_budget")
