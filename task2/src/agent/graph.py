"""步骤依赖，以及失败后如何挑选仍可执行的方案。"""

from __future__ import annotations

# 后一步只依赖前一步的成功结果。素材检索被所有方案共用。
DEPENDENCIES = {
    "material_search": [],
    "script_generate": ["material_search"],
    "cost_estimate": ["script_generate"],
    "plan_save": ["cost_estimate"],
}


def found_ids_from_search(result: dict | None) -> set[str]:
    if not isinstance(result, dict) or result.get("ok") is False:
        return set()
    return {item["id"] for item in result.get("materials", []) if "id" in item}


def missing_materials(plan: dict, found_ids: set[str]) -> list[dict]:
    return [item for item in plan["materials"] if item["id"] not in found_ids]


def script_material_ids(plan: dict, found_ids: set[str]) -> list[str]:
    return [item["id"] for item in plan["materials"] if item["id"] in found_ids]


def feasible_plans(plans: list[dict], current_id: str | None, found_ids: set[str], blocked_ids: set[str]) -> list[dict]:
    candidates = []
    for plan in plans:
        if plan["id"] == current_id or plan["id"] in blocked_ids:
            continue
        if missing_materials(plan, found_ids):
            continue
        candidates.append(plan)
    return candidates


def choose_next(plans: list[dict], current_id: str | None, found_ids: set[str], blocked_ids: set[str]) -> dict | None:
    candidates = feasible_plans(plans, current_id, found_ids, blocked_ids)
    if not candidates:
        return None
    return min(candidates, key=lambda plan: (plan["estimate"], plan["id"]))
