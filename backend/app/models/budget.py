from datetime import date, datetime

from sqlalchemy import Column, Date, Float, ForeignKey, Integer, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class BudgetCategory(Base):
    """Общая иерархия категорий бюджета (доход/расход). Не связана с метками заметок."""

    __tablename__ = "budget_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("budget_categories.id", ondelete="CASCADE"), nullable=True, index=True
    )

    parent: Mapped["BudgetCategory | None"] = relationship(
        "BudgetCategory",
        remote_side="BudgetCategory.id",
        back_populates="children",
    )
    children: Mapped[list["BudgetCategory"]] = relationship(
        "BudgetCategory",
        back_populates="parent",
    )


class BudgetLabel(Base):
    """Общие метки операций бюджета (отдельно от меток заметок)."""

    __tablename__ = "budget_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("budget_labels.id", ondelete="CASCADE"), nullable=True, index=True
    )

    parent: Mapped["BudgetLabel | None"] = relationship(
        "BudgetLabel",
        remote_side="BudgetLabel.id",
        back_populates="children",
    )
    children: Mapped[list["BudgetLabel"]] = relationship(
        "BudgetLabel",
        back_populates="parent",
    )


budget_transaction_labels = Table(
    "budget_transaction_labels",
    Base.metadata,
    Column(
        "transaction_id",
        Integer,
        ForeignKey("budget_transactions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "label_id",
        Integer,
        ForeignKey("budget_labels.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class BudgetTransaction(Base):
    __tablename__ = "budget_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    legacy_category: Mapped[str | None] = mapped_column("category", String(128), nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("budget_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    cat: Mapped["BudgetCategory | None"] = relationship(foreign_keys=[category_id])
    labels: Mapped[list["BudgetLabel"]] = relationship(
        secondary=budget_transaction_labels,
        lazy="selectin",
    )


class BudgetTemplate(Base):
    __tablename__ = "budget_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("budget_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    cat: Mapped["BudgetCategory | None"] = relationship(foreign_keys=[category_id])


class BudgetCommentCategoryRule(Base):
    __tablename__ = "budget_comment_category_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    pattern: Mapped[str] = mapped_column(String(512), nullable=False)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("budget_categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    cat: Mapped["BudgetCategory"] = relationship(foreign_keys=[category_id])


class BudgetCommentLabelRule(Base):
    __tablename__ = "budget_comment_label_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    pattern: Mapped[str] = mapped_column(String(512), nullable=False)
    label_id: Mapped[int] = mapped_column(
        ForeignKey("budget_labels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    label: Mapped["BudgetLabel"] = relationship(foreign_keys=[label_id])
