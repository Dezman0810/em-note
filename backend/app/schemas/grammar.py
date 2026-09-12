from pydantic import BaseModel, Field

GRAMMAR_MAX_CHARS = 8000


class GrammarCheckRequest(BaseModel):
    text: str = Field(min_length=1, max_length=GRAMMAR_MAX_CHARS)


class GrammarIssue(BaseModel):
    offset: int
    length: int
    message: str
    short_message: str = ""
    replacements: list[str] = []
    issue_type: str = ""


class GrammarSegment(BaseModel):
    text: str
    kind: str = "ok"  # ok | error | fix
    message: str = ""
    before: str = ""
    after: str = ""


class GrammarChange(BaseModel):
    before: str
    after: str
    message: str = ""
    kind: str = ""  # spelling | punctuation | grammar


class GrammarSuggestion(BaseModel):
    id: str
    label: str
    text: str
    change_count: int = 0
    original_parts: list[GrammarSegment] = []
    revised_parts: list[GrammarSegment] = []
    changes: list[GrammarChange] = []


class GrammarAdvice(BaseModel):
    before: str
    after: str
    message: str = ""
    options: list[str] = []


class GrammarCheckResponse(BaseModel):
    original: str
    suggestions: list[GrammarSuggestion]
    issues: list[GrammarIssue]
    advice: list[GrammarAdvice] = []
    language: str = ""
