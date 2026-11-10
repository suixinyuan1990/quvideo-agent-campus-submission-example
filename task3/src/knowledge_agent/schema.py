from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal[
    "answered",
    "conflict",
    "insufficient_evidence",
    "needs_clarification",
    "tool_failure",
]
ActionName = Literal["search", "read", "ask", "finish"]


class Citation(BaseModel):
    doc_id: str
    version_date: str | None = None
    excerpt: str


class Answer(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    status: Status


class Action(BaseModel):
    action: ActionName
    query: str | None = None
    doc_id: str | None = None
    question: str | None = None
    result: Answer | None = None
    reason: str = ""


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class TraceEvent(BaseModel):
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None


class RunResult(BaseModel):
    answer: Answer
    trace: list[TraceEvent]
