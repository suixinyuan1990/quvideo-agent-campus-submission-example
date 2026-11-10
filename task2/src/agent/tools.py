"""四个工具。费用只来自合成数据，调用方不能改价。"""

from __future__ import annotations

TOOL_TITLES = {
    "material_search": "素材检索",
    "script_generate": "脚本生成",
    "cost_estimate": "成本估算",
    "plan_save": "方案保存",
}
FAIL_MESSAGE = {
    "material_search": "素材检索失败",
    "script_generate": "脚本生成失败",
    "cost_estimate": "成本估算失败",
    "plan_save": "方案保存失败",
}


def consume_fail_once(tool: str, fail_once: list[str], runtime: dict) -> bool:
    if tool not in fail_once:
        return False
    used = runtime.setdefault("fail_once_used", [])
    if tool in used:
        return False
    used.append(tool)
    return True


def plan_tool_failed(tool: str, plan_id: str | None, fail_plan_tools: dict | None) -> bool:
    if not plan_id or not fail_plan_tools:
        return False
    return tool in fail_plan_tools.get(plan_id, [])


def invoke(
    tool: str,
    payload: dict,
    fail_tools: list[str],
    fail_once: list[str] | None = None,
    runtime: dict | None = None,
    plan_id: str | None = None,
    fail_plan_tools: dict | None = None,
) -> dict:
    runtime = {} if runtime is None else runtime
    injected = tool in fail_tools or plan_tool_failed(tool, plan_id, fail_plan_tools) or consume_fail_once(tool, list(fail_once or []), runtime)
    if injected:
        return {"ok": False, "error": "TOOL_ERROR", "message": FAIL_MESSAGE[tool]}
    return {"ok": True, **payload}


def split_materials(plans: list[dict]) -> tuple[list[dict], list[dict]]:
    materials = [item for plan in plans for item in plan["materials"]]
    available = [item for item in materials if item.get("available", True)]
    missing = [item for item in materials if not item.get("available", True)]
    return available, missing


def search_body(plans: list[dict]) -> dict:
    available, missing = split_materials(plans)
    body = {"count": len(available), "materials": available}
    if missing:
        body["missing"] = [item["title"] for item in missing]
        body["partial"] = True
    return body


def unavailable_materials(plan: dict) -> list[dict]:
    return [item for item in plan["materials"] if not item.get("available", True)]


def estimate_payload(plan: dict, budget: int, hours: int, unit: str) -> dict:
    material_cost = sum(item["cost"] for item in plan["materials"] if item.get("available", True))
    script_cost = plan["script"]["cost"]
    estimate = material_cost + script_cost
    within_budget = estimate <= budget
    within_deadline = plan["duration_hours"] <= hours
    return {
        "plan_id": plan["id"],
        "name": plan["name"],
        "material_cost": material_cost,
        "script_cost": script_cost,
        "estimate": estimate,
        "budget": budget,
        "within_budget": within_budget,
        "over_by": max(0, estimate - budget),
        "duration_hours": plan["duration_hours"],
        "available_hours": hours,
        "within_deadline": within_deadline,
        "unit": unit,
    }
