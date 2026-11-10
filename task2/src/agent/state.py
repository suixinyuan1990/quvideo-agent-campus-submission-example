"""运行状态、费用和输出组装。"""

from __future__ import annotations

import json

from src.agent.trace import Recorder

UNIT = "模拟单位"


def input_key(case: dict) -> str:
    return json.dumps(
        {
            "theme": case.get("theme"),
            "budget": case.get("budget"),
            "deadline": case.get("deadline"),
            "plan_set": case.get("plan_set"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def base_output(case: dict) -> dict:
    return {
        "case_id": case["case_id"],
        "note": case.get("note"),
        "theme": case.get("theme"),
        "budget": case.get("budget"),
        "deadline": case.get("deadline"),
        "unit": UNIT,
        "completed": False,
        "reused": False,
        "task_plan": [],
        "step_status": [],
        "tool_results": [],
        "decisions": [],
        "total_cost": 0,
        "incremental_cost": 0,
        "saved_plan": None,
        "incomplete_reason": None,
        "gap": None,
        "failed_steps_marked_success": False,
    }


def finalize(output: dict, recorder: Recorder, budget: int | None, decision_source: str = "local_policy") -> tuple[dict, dict]:
    for step in recorder.steps:
        result = step.get("result")
        if isinstance(result, dict) and result.get("ok") is False and step["status"] != "failed":
            raise RuntimeError("不能把失败步骤记为成功")
    output["task_plan"] = [
        {
            "id": step["id"],
            "tool": step["tool"],
            "title": step["title"],
            "plan_id": step.get("plan_id"),
        }
        for step in recorder.steps
    ]
    output["step_status"] = [
        {
            "id": step["id"],
            "tool": step["tool"],
            "title": step["title"],
            "plan_id": step.get("plan_id"),
            "status": step["status"],
            "reason": step.get("reason"),
            "prior_status": step.get("prior_status"),
            "executed_this_run": step.get("executed_this_run", step["status"] in {"success", "failed"}),
        }
        for step in recorder.steps
    ]
    output["tool_results"] = [
        {
            "id": step["id"],
            "tool": step["tool"],
            "plan_id": step.get("plan_id"),
            "status": step["status"],
            "result": step.get("result"),
            "retained_result": step.get("retained_result"),
            "source": step.get("source"),
        }
        for step in recorder.steps
        if step["status"] != "not_run" or step.get("result") is not None or step.get("retained_result") is not None
    ]
    output["decisions"] = [event for event in recorder.events if event["type"] == "decision"]
    output["failed_steps_marked_success"] = False
    if output["completed"]:
        if output["saved_plan"] is None:
            raise RuntimeError("已完成运行必须有已保存方案")
        if budget is None or output["total_cost"] > budget:
            raise RuntimeError("超预算方案不能记为已保存")
    elif output["saved_plan"] is not None:
        raise RuntimeError("未完成运行不能带已保存方案")
    trace = {
        "case_id": output["case_id"],
        "decision_source": decision_source,
        "events": recorder.events,
    }
    return output, trace
