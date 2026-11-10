"""Trace 记录。失败的工具结果不能写成 success。"""

from __future__ import annotations


class Recorder:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.steps: list[dict] = []
        self.seq = 0

    def event(self, payload: dict) -> dict:
        self.seq += 1
        item = {"seq": self.seq, **payload}
        self.events.append(item)
        return item

    def step(self, tool: str, status: str, title: str, request: dict | None, result: dict | None, **extra) -> dict:
        if isinstance(result, dict) and result.get("ok") is False and status != "failed":
            raise RuntimeError("不能把失败步骤记为成功")
        if status == "success" and isinstance(result, dict) and result.get("ok") is False:
            raise RuntimeError("不能把失败步骤记为成功")
        self.seq += 1
        step = {
            "id": f"s{len(self.steps) + 1}",
            "seq": self.seq,
            "tool": tool,
            "title": title,
            "status": status,
            "request": request,
            "result": result,
            **extra,
        }
        self.steps.append(step)
        self.events.append(
            {
                "seq": self.seq,
                "type": "tool",
                "tool": tool,
                "title": title,
                "status": status,
                "plan_id": extra.get("plan_id"),
                "request": request,
                "result": result,
                "reason": extra.get("reason"),
            }
        )
        return step

    def decision(self, action: str, rule: str, reason: str, **extra) -> dict:
        return self.event({"type": "decision", "action": action, "rule": rule, "reason": reason, **extra})
