from datetime import date as date_type
from pydantic import BaseModel, Field, field_validator


class TransactionCreate(BaseModel):
    kind: str = Field(description="income or expense")
    amount: float = Field(gt=0)
    category_id: int | None = None
    note: str | None = None
    occurred_on: date_type | None = None
    label_ids: list[int] = Field(default_factory=list)
    merge_comment_label_rules: bool = Field(
        default=True,
        description="Если True, к выбранным меткам добавляются метки по правилам regex в комментарии",
    )

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, v: str) -> str:
        low = v.lower().strip()
        if low not in ("income", "expense"):
            raise ValueError("kind must be income or expense")
        return low

    @field_validator("label_ids")
    @classmethod
    def dedupe_label_ids(cls, v: list[int]) -> list[int]:
        return list(dict.fromkeys(v))


class TransactionPatch(BaseModel):
    kind: str | None = None
    amount: float | None = Field(default=None, gt=0)
    category_id: int | None = None
    note: str | None = None
    occurred_on: date_type | None = None
    label_ids: list[int] | None = None
    merge_comment_label_rules: bool | None = Field(
        default=None,
        description="При передаче label_ids: объединять ли с авто-метками по regex (по умолчанию True)",
    )

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, v: str | None) -> str | None:
        if v is None:
            return None
        low = v.lower().strip()
        if low not in ("income", "expense"):
            raise ValueError("kind must be income or expense")
        return low

    @field_validator("label_ids")
    @classmethod
    def dedupe_label_ids_patch(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        return list(dict.fromkeys(v))


class LabelOut(BaseModel):
    id: int
    kind: str
    name: str
    parent_id: int | None = None
    path: str | None = None

    model_config = {"from_attributes": True}


class TransactionOut(BaseModel):
    id: int
    kind: str
    amount: float
    category_id: int | None = None
    category_path: str | None = None
    legacy_category: str | None = None
    note: str | None = None
    occurred_on: date_type
    labels: list[LabelOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class StatsDaily(BaseModel):
    day: date_type
    income: float
    expense: float


class StatsCategory(BaseModel):
    category: str
    amount: float


class StatsTotals(BaseModel):
    """Суммы доходов и расходов; для /stats/totals можно ограничить датами."""

    total_income: float
    total_expense: float
    balance: float


class CategoryCreate(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=128)
    parent_id: int | None = None

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, v: str) -> str:
        low = v.lower().strip()
        if low not in ("income", "expense"):
            raise ValueError("kind must be income or expense")
        return low

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("name required")
        return s


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    parent_id: int | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None


class CategoryOut(BaseModel):
    id: int
    kind: str
    name: str
    parent_id: int | None = None

    model_config = {"from_attributes": True}


class TemplateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    kind: str
    amount: float = Field(gt=0)
    category_id: int | None = None
    note: str | None = None

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, v: str) -> str:
        low = v.lower().strip()
        if low not in ("income", "expense"):
            raise ValueError("kind must be income or expense")
        return low

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip()


class TemplatePatch(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    kind: str | None = None
    amount: float | None = Field(default=None, gt=0)
    category_id: int | None = None
    note: str | None = None


class TemplateOut(BaseModel):
    id: int
    title: str
    kind: str
    amount: float
    category_id: int | None = None
    category_path: str | None = None
    note: str | None = None

    model_config = {"from_attributes": True}


class FromTemplateBody(BaseModel):
    occurred_on: date_type | None = None


class CommentRuleCreate(BaseModel):
    kind: str
    pattern: str = Field(min_length=1, max_length=512)
    category_id: int = Field(gt=0)
    sort_order: int = Field(default=100, ge=0, le=999_999)
    title: str | None = Field(default=None, max_length=160)

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, v: str) -> str:
        low = v.lower().strip()
        if low not in ("income", "expense"):
            raise ValueError("kind must be income or expense")
        return low


class CommentRulePatch(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=512)
    category_id: int | None = Field(default=None, gt=0)
    sort_order: int | None = Field(default=None, ge=0, le=999_999)
    title: str | None = Field(default=None, max_length=160)


class CommentRuleOut(BaseModel):
    id: int
    kind: str
    title: str | None
    pattern: str
    category_id: int
    category_path: str | None = None
    sort_order: int

    model_config = {"from_attributes": True}


class LabelCreate(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=128)
    parent_id: int | None = None

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, v: str) -> str:
        low = v.lower().strip()
        if low not in ("income", "expense"):
            raise ValueError("kind must be income or expense")
        return low

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("name required")
        return s


class LabelPatch(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    parent_id: int | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None


class CommentLabelRuleCreate(BaseModel):
    kind: str
    pattern: str = Field(min_length=1, max_length=512)
    label_id: int = Field(gt=0)
    sort_order: int = Field(default=100, ge=0, le=999_999)
    title: str | None = Field(default=None, max_length=160)

    @field_validator("kind")
    @classmethod
    def normalize_kind(cls, v: str) -> str:
        low = v.lower().strip()
        if low not in ("income", "expense"):
            raise ValueError("kind must be income or expense")
        return low


class CommentLabelRulePatch(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=512)
    label_id: int | None = Field(default=None, gt=0)
    sort_order: int | None = Field(default=None, ge=0, le=999_999)
    title: str | None = Field(default=None, max_length=160)


class CommentLabelRuleOut(BaseModel):
    id: int
    kind: str
    title: str | None
    pattern: str
    label_id: int
    label_name: str | None = None
    label_path: str | None = None
    sort_order: int

    model_config = {"from_attributes": True}
