"""无密钥时的本地规则。文案与既有 Trace 保持一致。"""

from __future__ import annotations


def missing_reason(missing: list[str]) -> str:
    return "缺少" + "、".join(missing) + "，不补造缺失字段，方案未保存。"


def reuse_reason() -> str:
    return "同一输入已有已保存方案，沿用该方案，跳过已完成步骤，本次不新增费用。"


def empty_material_reason() -> str:
    return "无可用素材，方案未保存。"


def tool_failure_reason(message: str, search: bool = False) -> str:
    if search:
        return message + "。已停止，方案未保存。"
    return message + "。失败步骤保持 failed，方案未保存。"


def save_failure_reason(message: str) -> str:
    return message + "。方案未保存。"


def switch_over_budget(plan: dict, estimate: int, budget: int, nxt: dict) -> str:
    return f"{plan['name']}估算 {estimate}，预算 {budget}，超出 {estimate - budget}。改选{nxt['name']}，准备再次估算。"


def save_rule(rejected: list[dict]) -> str:
    return "R1" if rejected else "R7"


def save_reason(plan: dict, estimate: int, budget: int) -> str:
    return f"{plan['name']}估算 {estimate}，未超过预算 {budget}，保存该方案。"


def gap_reason(lowest: int, budget: int, shortfall: int) -> str:
    return f"没有可行方案。最低估算 {lowest} 个模拟单位，预算 {budget}，缺口 {shortfall}。"


def partial_switch_reason(plan: dict, names: str, nxt: dict) -> str:
    return f"{plan['name']}缺少{names}，无法形成完整方案。改选{nxt['name']}。"


def partial_stop_reason(names: str) -> str:
    return f"缺少资料：{names}。方案未保存。"


def resume_reason(failed_tool_message: str) -> str:
    return f"从失败步骤继续：{failed_tool_message}。已成功步骤不重复执行，费用不重算。"


def replan_after_failure(plan_name: str, message: str, retained: str, next_name: str) -> str:
    return f"{plan_name}{message}。{retained}，改选{next_name}。"
