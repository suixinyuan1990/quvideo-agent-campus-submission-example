"""硬约束。模型可以提议保存，超预算或失败结果仍然不能通过。"""

from __future__ import annotations

ACTIONS = {"continue", "switch", "retry", "save", "stop", "reuse"}


def missing_fields(case: dict) -> list[str]:
    missing = []
    if case.get("budget") is None:
        missing.append("预算")
    if not case.get("deadline"):
        missing.append("截止时间")
    return missing


def allow_save(within_budget: bool, within_deadline: bool) -> bool:
    return bool(within_budget) and bool(within_deadline)


def review_action(action: dict, observation: dict) -> tuple[bool, str]:
    name = action.get("action")
    if name not in ACTIONS:
        return False, "无法解析的动作。该决策不记为成功步骤，方案未保存。"
    if observation.get("missing_fields") and name != "stop":
        return False, "缺少预算或截止时间，不能继续执行工具。"
    if name == "save":
        if not observation.get("estimate_ready"):
            return False, "还没有成功的成本估算，拒绝保存。"
        if not allow_save(bool(observation.get("within_budget")), bool(observation.get("within_deadline"))):
            estimate = observation.get("estimate")
            budget = observation.get("budget")
            return False, f"估算 {estimate} 超过预算 {budget} 或赶不上截止时间，拒绝保存。"
    if name == "switch" and action.get("to_plan") not in observation.get("remaining_plan_ids", []):
        return False, "没有可改选的方案。"
    if name == "retry" and observation.get("last_status") != "failed":
        return False, "没有失败步骤需要重试。"
    if name == "continue" and observation.get("blocked_continue"):
        if observation.get("last_status") == "failed":
            return False, "当前步骤已失败，依赖未满足，不能沿原计划继续。"
        return False, "当前方案不可继续保存，需要改选或停止。"
    return True, ""
