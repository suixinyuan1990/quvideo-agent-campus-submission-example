"""Actions, drafts, tool results, and the creator-facing delivery."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class Attribute(BaseModel):
    key: str
    value: str


class Material(BaseModel):
    source_id: str
    body: str
    attributes: list[Attribute] = Field(default_factory=list)
    split: str | None = None
    row_index: int | None = None
    dataset: str | None = None


class Request(BaseModel):
    theme: str | None = None
    duration_sec: float | None = None
    audience: str | None = None
    platform: str | None = None
    style: str | None = None

    @property
    def effective_style(self) -> str:
        return self.style or "口播"


class ShotDraft(BaseModel):
    index: int
    visual: str
    narration: str = ""
    subtitle: str = ""
    source_ids: list[str] = Field(default_factory=list)


class Draft(BaseModel):
    title: str
    shots: list[ShotDraft]


class ShotDelivery(BaseModel):
    index: int
    visual: str
    narration: str
    subtitle: str
    source_ids: list[str]
    duration_sec: float


class Hit(BaseModel):
    source_id: str
    body: str
    attributes: list[Attribute]
    matched_values: list[str]
    score: float


class ShotTiming(BaseModel):
    index: int
    duration_ms: int
    duration_sec: float
    spoken_chars: int


class Estimate(BaseModel):
    total_ms: int
    total_sec: float
    shots: list[ShotTiming]
    chars_per_second: float


class Violation(BaseModel):
    rule_id: str
    location: str
    message: str
    blocking: bool


class CheckResult(BaseModel):
    passed: bool
    violations: list[Violation] = Field(default_factory=list)


class Rule(BaseModel):
    rule_id: str
    blocking: bool = True
    kind: Literal["forbid_regex", "require_substring"]
    pattern: str | None = None
    phrase: str | None = None
    note: str = ""


class SearchAction(BaseModel):
    action: Literal["search"]
    query: str


class DraftAction(BaseModel):
    action: Literal["draft"]
    title: str
    shots: list[ShotDraft]


class EstimateAction(BaseModel):
    action: Literal["estimate"]


class CheckAction(BaseModel):
    action: Literal["check_rules"]


class AskAction(BaseModel):
    action: Literal["ask"]
    missing: list[str] = Field(default_factory=list)
    message: str


class FinishAction(BaseModel):
    action: Literal["finish"]
    status: Literal["completed", "no_material", "unsatisfied", "needs_input"]
    message: str = ""


Action = Annotated[
    SearchAction | DraftAction | EstimateAction | CheckAction | AskAction | FinishAction,
    Field(discriminator="action"),
]


class Result(BaseModel):
    title: str = ""
    shots: list[ShotDelivery] = Field(default_factory=list)
    estimated_duration_sec: float | None = None
    source_ids: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    status: Literal["completed", "needs_input", "no_material", "tool_failure", "unsatisfied"]
    message: str = ""


class RunOutput(BaseModel):
    input: Request
    result: Result
    trace: list[dict]
