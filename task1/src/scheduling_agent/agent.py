"""ReAct 执行循环。

循环本身只做四件事：请模型选择动作、执行工具、记录观察、再请模型决定下一步或结束。
风险、冲突、补查和确认都在决策模型里。达到步数或工具次数上限时返回未完成，不继续调用工具。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from scheduling_agent.catalog import DataCatalog
from scheduling_agent.model import ObservationDecisionModel
from scheduling_agent.report import RunMeta, build_report
from scheduling_agent.store import DraftStore
from scheduling_agent.tools import Toolset
from scheduling_agent.types import Decision, ModelOutputError, Observation

DEFAULT_MAX_STEPS = 8
DEFAULT_MAX_TOOL_CALLS = 8
RUNNER_ONLY_KEYS = ("repeat",)


def project_root() -> Path:
    env = os.environ.get("SCHEDULING_AGENT_ROOT")
    if env:
        return Path(env)
    cwd = Path.cwd()
    if (cwd / "data" / "materials.json").exists():
        return cwd
    return Path(__file__).resolve().parents[2]


def run_input(
    payload: dict[str, Any],
    *,
    data_dir: str | Path,
    store_path: str | Path,
    model: Any | None = None,
    max_steps: int | None = None,
    max_tool_calls: int | None = None,
) -> dict[str, Any]:
    request = dict(payload)
    repeat = int(request.pop("repeat", 1) or 1)
    if repeat < 1:
        repeat = 1
    runs = [
        run_task(
            request,
            data_dir=data_dir,
            store_path=store_path,
            model=model,
            max_steps=max_steps,
            max_tool_calls=max_tool_calls,
        )
        for _ in range(repeat)
    ]
    store = DraftStore(store_path)
    if repeat == 1:
        return {"output": runs[0]["result"], "trace": runs[0]["trace"]}
    return {
        "output": {
            "repeat": repeat,
            "store_draft_count": store.count(),
            "drafts": store.list_drafts(),
            "runs": [item["result"] for item in runs],
        },
        "trace": {
            "repeat": repeat,
            "store_draft_count": store.count(),
            "runs": [item["trace"] for item in runs],
        },
    }


def run_task(
    request: dict[str, Any],
    *,
    data_dir: str | Path,
    store_path: str | Path,
    model: Any | None = None,
    max_steps: int | None = None,
    max_tool_calls: int | None = None,
) -> dict[str, Any]:
    clean_request = {key: value for key, value in request.items() if key not in RUNNER_ONLY_KEYS}
    limits = resolve_limits(clean_request, max_steps=max_steps, max_tool_calls=max_tool_calls)
    catalog = DataCatalog(data_dir)
    store = DraftStore(store_path)
    tools = Toolset(catalog, store, clean_request.get("confirmed_slot"))
    policy = model or ObservationDecisionModel()
    observations: list[Observation] = []
    steps: list[dict[str, Any]] = []
    decision_count = 0
    tool_calls = 0
    stopped: dict[str, Any] | None = None
    final_decision: dict[str, Any] | None = None
    incomplete_reason: str | None = None

    while True:
        if decision_count >= limits["max_steps"]:
            incomplete_reason = f"已达到执行步数上限（{limits['max_steps']}），任务未完成"
            stopped = {"reason": "max_steps", "executed": False}
            _blank_next(steps)
            break
        try:
            decision = policy.decide(clean_request, observations)
        except ModelOutputError as exc:
            incomplete_reason = f"模型未返回可执行动作，任务未完成：{exc}"
            stopped = {"reason": "model_output", "executed": False}
            final_decision = {"action": "finish", "arguments": None, "decision_basis": incomplete_reason}
            _blank_next(steps)
            break
        decision_count += 1
        _link_previous(steps, decision)
        if decision.kind == "finish":
            final_decision = _decision_record(decision)
            break
        if tool_calls >= limits["max_tool_calls"]:
            incomplete_reason = f"已达到工具调用次数上限（{limits['max_tool_calls']}），任务未完成"
            stopped = {
                "reason": "max_tool_calls",
                "executed": False,
                "attempted_action": decision.action,
                "attempted_arguments": dict(decision.arguments),
                "decision_basis": decision.rationale,
            }
            final_decision = _decision_record(decision)
            break
        arguments = dict(decision.arguments)
        payload = tools.call(decision.tool or "", arguments)
        tool_calls += 1
        observation = Observation(
            step=tool_calls,
            tool=decision.tool or "",
            arguments=arguments,
            ok=bool(payload.get("ok")),
            summary=str(payload.get("summary") or ""),
            payload=payload,
        )
        observations.append(observation)
        steps.append(
            {
                "step": tool_calls,
                "tool": observation.tool,
                "arguments": arguments,
                "decision_basis": decision.rationale,
                "result_summary": observation.summary,
                "result": payload,
            }
        )

    run_status = "incomplete" if incomplete_reason else "completed"
    meta = RunMeta(
        run_status=run_status,
        incomplete_reason=incomplete_reason,
        decision_count=decision_count,
        tool_calls_used=tool_calls,
        max_steps=limits["max_steps"],
        max_tool_calls=limits["max_tool_calls"],
        store_draft_count=store.count(),
    )
    result = build_report(clean_request, observations, meta)
    trace = {
        "run_status": result["run_status"],
        "outcome": result["outcome"],
        "material_id": result["material_id"],
        "max_steps": limits["max_steps"],
        "max_tool_calls": limits["max_tool_calls"],
        "decision_count": decision_count,
        "tool_calls_used": tool_calls,
        "hit_limit": run_status == "incomplete",
        "incomplete_reason": incomplete_reason,
        "stopped": stopped,
        "final_decision": final_decision,
        "steps": steps,
    }
    return {"result": result, "trace": trace}


def resolve_limits(
    request: dict[str, Any],
    *,
    max_steps: int | None,
    max_tool_calls: int | None,
) -> dict[str, int]:
    return {
        "max_steps": _pick_limit(max_steps, request.get("max_steps"), "AGENT_MAX_STEPS", DEFAULT_MAX_STEPS),
        "max_tool_calls": _pick_limit(
            max_tool_calls,
            request.get("max_tool_calls"),
            "AGENT_MAX_TOOL_CALLS",
            DEFAULT_MAX_TOOL_CALLS,
        ),
    }


def _pick_limit(explicit: int | None, request_value: Any, env_name: str, default: int) -> int:
    if explicit is not None:
        return int(explicit)
    if request_value is not None:
        return int(request_value)
    env_value = os.environ.get(env_name)
    if env_value:
        return int(env_value)
    return default


def _decision_record(decision: Decision) -> dict[str, Any]:
    return {
        "action": decision.action,
        "arguments": None if decision.kind == "finish" else dict(decision.arguments),
        "decision_basis": decision.rationale,
    }


def _link_previous(steps: list[dict[str, Any]], decision: Decision) -> None:
    if not steps:
        return
    steps[-1]["next_action"] = decision.action
    steps[-1]["next_arguments"] = None if decision.kind == "finish" else dict(decision.arguments)
    steps[-1]["next_decision_basis"] = decision.rationale


def _blank_next(steps: list[dict[str, Any]]) -> None:
    if not steps or "next_action" in steps[-1]:
        return
    steps[-1]["next_action"] = None
    steps[-1]["next_arguments"] = None
    steps[-1]["next_decision_basis"] = None
