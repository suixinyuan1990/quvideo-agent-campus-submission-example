"""ReAct 循环里流转的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TOOL_NAMES = ("read_material", "check_rules", "query_slots", "save_draft")


@dataclass
class Observation:
    """一次已经执行完的工具调用。决策函数只能看见这些结果，不能预读下一次调用。"""

    step: int
    tool: str
    arguments: dict[str, Any]
    ok: bool
    summary: str
    payload: dict[str, Any]


@dataclass
class Decision:
    """模型本轮输出：调用一个工具，或结束。"""

    kind: str
    rationale: str
    tool: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)

    @property
    def action(self) -> str:
        if self.kind == "finish":
            return "finish"
        return self.tool or ""


class ModelOutputError(Exception):
    """远程模型没有返回可执行动作。循环不会自动再问一次。"""


class ModelConfigError(Exception):
    """选择了远程模型，但没有配齐地址、密钥或模型名。"""
