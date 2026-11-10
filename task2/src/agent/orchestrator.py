"""观察、决策、守卫、工具和状态写回。"""

from __future__ import annotations

import copy
from datetime import datetime

from src.agent import guard, policy
from src.agent.disk_state import load_state, save_state
from src.agent.files import ROOT, load_json
from src.agent.graph import choose_next, feasible_plans, found_ids_from_search, missing_materials, script_material_ids
from src.agent.state import UNIT, base_output, finalize, input_key
from src.agent.tools import FAIL_MESSAGE, TOOL_TITLES, estimate_payload, invoke, search_body
from src.agent.trace import Recorder


def available_hours(as_of: str, deadline: str) -> int:
    start = datetime.fromisoformat(as_of)
    end = datetime.fromisoformat(f"{deadline}T23:59:59")
    return int((end - start).total_seconds() // 3600)


def load_plan_set(plan_set: str) -> dict:
    catalog = load_json(ROOT / "data" / "plans.json")
    entry = catalog["sets"][plan_set]
    for plan in entry["plans"]:
        material_cost = sum(item["cost"] for item in plan["materials"])
        script_cost = plan["script"]["cost"]
        total = material_cost + script_cost
        if total != plan["estimate"]:
            raise ValueError(f"{plan['id']} 的估算 {plan['estimate']} 与明细 {total} 不一致")
    return entry


def finish_incomplete(output: dict, recorder: Recorder, reason: str, gap: dict | None, budget: int | None, decision_source: str = "local_policy") -> tuple[dict, dict]:
    output["completed"] = False
    output["incomplete_reason"] = reason
    output["gap"] = gap
    output["saved_plan"] = None
    output["total_cost"] = 0
    output["incremental_cost"] = 0
    return finalize(output, recorder, budget, decision_source)


def remember_incomplete(case: dict, store: dict, key: str, recorder: Recorder, failed_tool: str, plan_index: int) -> None:
    if not case.get("resume"):
        return
    store[key] = {
        "incomplete": True,
        "saved_plan": None,
        "total_cost": 0,
        "steps": copy.deepcopy(recorder.steps),
        "failed_tool": failed_tool,
        "plan_index": plan_index,
    }


def success_steps(steps: list[dict]) -> dict[tuple, dict]:
    found = {}
    for step in steps:
        if step["status"] == "success":
            found[(step["tool"], step.get("plan_id"))] = step
    return found


def reuse_run(case: dict, hit: dict) -> tuple[dict, dict]:
    recorder = Recorder()
    output = base_output(case)
    output["reused"] = True
    output["completed"] = True
    output["saved_plan"] = copy.deepcopy(hit["saved_plan"])
    output["total_cost"] = hit["total_cost"]
    output["incremental_cost"] = 0
    reason = policy.reuse_reason()
    recorder.decision(
        "reuse",
        "R6",
        reason,
        saved_plan_id=hit["saved_plan"]["plan_id"],
        retained_total_cost=hit["total_cost"],
        incremental_cost=0,
    )
    for previous in hit["steps"]:
        recorder.step(
            previous["tool"],
            "skipped",
            previous["title"],
            None,
            None,
            plan_id=previous.get("plan_id"),
            reason="已完成，不重复执行",
            prior_status=previous["status"],
            executed_this_run=False,
            retained_result=copy.deepcopy(previous.get("result")),
            source="previous_run",
        )
    return finalize(output, recorder, case.get("budget"))


def mark_not_run(recorder: Recorder, tools: list[str], reason: str) -> None:
    for tool in tools:
        recorder.step(tool, "not_run", TOOL_TITLES[tool], None, None, reason=reason, executed_this_run=False)


def skip_success(recorder: Recorder, previous: dict) -> None:
    recorder.step(
        previous["tool"],
        "skipped",
        previous["title"],
        None,
        None,
        plan_id=previous.get("plan_id"),
        reason="已完成，不重复执行",
        prior_status="success",
        executed_this_run=False,
        retained_result=copy.deepcopy(previous.get("result")),
        source="previous_run",
    )


def run_once(case: dict, store: dict) -> tuple[dict, dict]:
    recorder = Recorder()
    output = base_output(case)
    budget = case.get("budget")
    missing = guard.missing_fields(case)
    if missing:
        reason = policy.missing_reason(missing)
        recorder.decision("stop", "R4", reason, missing_fields=missing)
        mark_not_run(recorder, list(TOOL_TITLES), reason)
        return finish_incomplete(output, recorder, reason, {"missing_fields": missing}, budget)

    runtime = store.setdefault("__runtime__", {})
    key = input_key(case)
    hit = store.get(key)
    if hit and hit.get("saved_plan"):
        return reuse_run(case, hit)

    plan_set = load_plan_set(case["plan_set"])
    plans = plan_set["plans"]
    fail_tools = list(plan_set.get("fail_tools", []))
    fail_once = list(plan_set.get("fail_once", []))
    fail_plan_tools = dict(plan_set.get("fail_plan_tools", {}))
    hours = available_hours(case["as_of"], case["deadline"])
    prior = hit if hit and hit.get("incomplete") and case.get("resume") else None
    done = success_steps(prior["steps"]) if prior else {}
    recorder.event(
        {
            "type": "plan_init",
            "decision_source": "local_policy",
            "budget": budget,
            "deadline": case["deadline"],
            "available_hours": hours,
            "plan_ids": [plan["id"] for plan in plans],
        }
    )
    if prior:
        recorder.decision(
            "retry",
            "R3",
            policy.resume_reason(FAIL_MESSAGE.get(prior.get("failed_tool"), "失败步骤")),
            failed_tool=prior.get("failed_tool"),
        )

    search_body_payload = search_body(plans)
    previous_search = done.get(("material_search", None))
    if previous_search:
        skip_success(recorder, previous_search)
        search_result = previous_search["result"]
        search_status = "skipped"
    else:
        search_result = invoke("material_search", search_body_payload, fail_tools, fail_once, runtime)
        search_status = "failed" if search_result.get("ok") is False else "success"
        recorder.step("material_search", search_status, TOOL_TITLES["material_search"], {"theme": case["theme"]}, search_result)
    if search_status == "failed":
        reason = policy.tool_failure_reason(search_result["message"], search=True)
        recorder.decision("stop", "R3", reason, failed_tool="material_search")
        mark_not_run(recorder, ["script_generate", "cost_estimate", "plan_save"], reason)
        remember_incomplete(case, store, key, recorder, "material_search", 0)
        return finish_incomplete(output, recorder, reason, None, budget)
    if not plans and not search_body_payload.get("materials"):
        reason = policy.empty_material_reason()
        recorder.decision("stop", "R5", reason, material_count=0)
        mark_not_run(recorder, ["script_generate", "cost_estimate", "plan_save"], reason)
        return finish_incomplete(output, recorder, reason, {"missing": "materials"}, budget)

    rejected = []
    blocked_ids: set[str] = set()
    found_ids = found_ids_from_search(search_result)
    index = 0
    visited = 0

    def go_next(plan: dict, record) -> bool:
        blocked_ids.add(plan["id"])
        nxt = choose_next(plans, plan["id"], found_ids, blocked_ids)
        if nxt is None:
            return False
        record(nxt)
        nonlocal index
        index = next(pos for pos, item in enumerate(plans) if item["id"] == nxt["id"])
        return True

    while index < len(plans) and visited <= len(plans):
        visited += 1
        plan = plans[index]
        missing_mats = missing_materials(plan, found_ids)
        if missing_mats:
            names = "、".join(item["title"] for item in missing_mats)

            def record_partial(nxt, names=names, plan=plan, missing_mats=missing_mats):
                recorder.decision(
                    "switch",
                    "R5",
                    policy.partial_switch_reason(plan, names, nxt),
                    from_plan=plan["id"],
                    to_plan=nxt["id"],
                    missing_materials=[item["title"] for item in missing_mats],
                    reason_code="dependency",
                )

            if go_next(plan, record_partial):
                continue
            reason = policy.partial_stop_reason(names)
            recorder.decision("stop", "R5", reason, missing_materials=[item["title"] for item in missing_mats])
            mark_not_run(recorder, ["script_generate", "cost_estimate", "plan_save"], reason)
            return finish_incomplete(output, recorder, reason, {"missing_materials": [item["title"] for item in missing_mats]}, budget)

        previous_script = done.get(("script_generate", plan["id"]))
        if previous_script:
            skip_success(recorder, previous_script)
            script_status = "skipped"
            script_result = previous_script["result"]
        else:
            script_request = {"plan_id": plan["id"], "theme": case["theme"], "material_ids": script_material_ids(plan, found_ids), "source": "material_search"}
            script_result = invoke(
                "script_generate",
                {"plan_id": plan["id"], "script": plan["script"]},
                fail_tools,
                fail_once,
                runtime,
                plan_id=plan["id"],
                fail_plan_tools=fail_plan_tools,
            )
            script_status = "failed" if script_result.get("ok") is False else "success"
            recorder.step(
                "script_generate",
                script_status,
                f"生成{plan['name']}脚本",
                script_request,
                script_result,
                plan_id=plan["id"],
            )
        if script_status == "failed":
            def record_script(nxt, plan=plan):
                recorder.decision(
                    "switch",
                    "R3",
                    policy.replan_after_failure(plan["name"], "的脚本生成失败", "已成功的素材检索结果保留", nxt["name"]),
                    from_plan=plan["id"],
                    to_plan=nxt["id"],
                    failed_tool="script_generate",
                    retained=["material_search"],
                    reason_code="dependency",
                )

            if go_next(plan, record_script):
                continue
            reason = policy.tool_failure_reason(script_result["message"])
            recorder.decision("stop", "R3", reason, failed_tool="script_generate", plan_id=plan["id"])
            mark_not_run(recorder, ["cost_estimate", "plan_save"], reason)
            remember_incomplete(case, store, key, recorder, "script_generate", index)
            return finish_incomplete(output, recorder, reason, None, budget)

        previous_estimate = done.get(("cost_estimate", plan["id"]))
        if previous_estimate:
            skip_success(recorder, previous_estimate)
            estimate_status = "skipped"
            estimate_result = previous_estimate["result"]
        else:
            usable = dict(plan)
            usable["materials"] = [item for item in plan["materials"] if item["id"] in found_ids]
            payload = estimate_payload(usable, budget, hours, UNIT)
            estimate_result = invoke(
                "cost_estimate",
                payload,
                fail_tools,
                fail_once,
                runtime,
                plan_id=plan["id"],
                fail_plan_tools=fail_plan_tools,
            )
            estimate_status = "failed" if estimate_result.get("ok") is False else "success"
            recorder.step(
                "cost_estimate",
                estimate_status,
                f"估算{plan['name']}",
                {"plan_id": plan["id"]},
                estimate_result,
                plan_id=plan["id"],
            )
        if estimate_status == "failed":
            def record_estimate(nxt, plan=plan):
                recorder.decision(
                    "switch",
                    "R3",
                    policy.replan_after_failure(plan["name"], "的成本估算失败", "已成功的素材检索和脚本结果保留", nxt["name"]),
                    from_plan=plan["id"],
                    to_plan=nxt["id"],
                    failed_tool="cost_estimate",
                    retained=["material_search", "script_generate"],
                    reason_code="dependency",
                )

            if go_next(plan, record_estimate):
                continue
            reason = policy.tool_failure_reason(estimate_result["message"])
            recorder.decision("stop", "R3", reason, failed_tool="cost_estimate", plan_id=plan["id"])
            mark_not_run(recorder, ["plan_save"], reason)
            remember_incomplete(case, store, key, recorder, "cost_estimate", index)
            return finish_incomplete(output, recorder, reason, None, budget)

        estimate = estimate_result["estimate"]
        within_budget = estimate_result["within_budget"]
        within_deadline = estimate_result["within_deadline"]
        if within_budget and within_deadline:
            if not guard.allow_save(within_budget, within_deadline):
                raise RuntimeError("超预算方案不能保存")
            saved = {
                "plan_id": plan["id"],
                "name": plan["name"],
                "theme": case["theme"],
                "materials": [item for item in plan["materials"] if item["id"] in found_ids],
                "script": plan["script"],
                "estimate": estimate,
                "duration_hours": plan["duration_hours"],
                "budget": budget,
                "deadline": case["deadline"],
                "unit": UNIT,
                "rejected_plans": rejected,
            }
            save_result = invoke(
                "plan_save",
                {"saved": True, "plan_id": plan["id"], "estimate": estimate},
                fail_tools,
                fail_once,
                runtime,
                plan_id=plan["id"],
                fail_plan_tools=fail_plan_tools,
            )
            save_status = "failed" if save_result.get("ok") is False else "success"
            if save_status == "failed":
                recorder.step("plan_save", "failed", f"保存{plan['name']}", {"plan_id": plan["id"]}, save_result, plan_id=plan["id"])

                def record_save(nxt, plan=plan):
                    recorder.decision(
                        "switch",
                        "R3",
                        policy.replan_after_failure(plan["name"], "的方案保存失败", "已成功的检索、脚本和估算结果保留", nxt["name"]),
                        from_plan=plan["id"],
                        to_plan=nxt["id"],
                        failed_tool="plan_save",
                        retained=["material_search", "script_generate", "cost_estimate"],
                        reason_code="dependency",
                    )

                if go_next(plan, record_save):
                    continue
                reason = policy.save_failure_reason(save_result["message"])
                recorder.decision("stop", "R3", reason, failed_tool="plan_save", plan_id=plan["id"])
                remember_incomplete(case, store, key, recorder, "plan_save", index)
                return finish_incomplete(output, recorder, reason, None, budget)
            recorder.decision(
                "save",
                policy.save_rule(rejected),
                policy.save_reason(plan, estimate, budget),
                plan_id=plan["id"],
                observed_estimate=estimate,
                budget=budget,
            )
            recorder.step("plan_save", "success", f"保存{plan['name']}", {"plan_id": plan["id"]}, save_result, plan_id=plan["id"])
            output["completed"] = True
            output["saved_plan"] = saved
            output["total_cost"] = estimate
            output["incremental_cost"] = estimate
            output["incomplete_reason"] = None
            output["gap"] = None
            store[key] = {
                "saved_plan": copy.deepcopy(saved),
                "total_cost": estimate,
                "steps": copy.deepcopy(recorder.steps),
            }
            return finalize(output, recorder, budget)

        rejected.append(
            {
                "plan_id": plan["id"],
                "name": plan["name"],
                "estimate": estimate,
                "over_by": max(0, estimate - budget),
                "within_deadline": within_deadline,
            }
        )
        def record_budget(nxt, plan=plan, estimate=estimate):
            recorder.decision(
                "switch",
                "R1",
                policy.switch_over_budget(plan, estimate, budget, nxt),
                from_plan=plan["id"],
                to_plan=nxt["id"],
                observed_estimate=estimate,
                budget=budget,
                reason_code="budget",
            )

        if go_next(plan, record_budget):
            continue
        break

    lowest = min(item["estimate"] for item in rejected)
    shortfall = lowest - budget
    gap = {
        "unit": UNIT,
        "budget": budget,
        "lowest_estimate": lowest,
        "shortfall": shortfall,
        "rejected": rejected,
    }
    reason = policy.gap_reason(lowest, budget, shortfall)
    recorder.decision("stop", "R2", reason, gap=gap)
    recorder.step("plan_save", "not_run", TOOL_TITLES["plan_save"], None, None, reason=reason, executed_this_run=False)
    return finish_incomplete(output, recorder, reason, gap, budget)


def run_model_once(case: dict, store: dict, decider) -> tuple[dict, dict]:
    recorder = Recorder()
    output = base_output(case)
    budget = case.get("budget")
    missing = guard.missing_fields(case)
    if missing:
        reason = policy.missing_reason(missing)
        recorder.decision("stop", "guard", reason, missing_fields=missing, proposed_by="guard", accepted=True)
        mark_not_run(recorder, list(TOOL_TITLES), reason)
        return finish_incomplete(output, recorder, reason, {"missing_fields": missing}, budget, "model")

    plan_set = load_plan_set(case["plan_set"])
    plans = plan_set["plans"]
    fail_tools = list(plan_set.get("fail_tools", []))
    fail_once = list(plan_set.get("fail_once", []))
    fail_plan_tools = dict(plan_set.get("fail_plan_tools", {}))
    runtime = store.setdefault("__runtime__", {})
    hours = available_hours(case["as_of"], case["deadline"]) if case.get("as_of") and case.get("deadline") else 0
    index = 0
    search_done = False
    script_done: set[str] = set()
    estimate_done: set[str] = set()
    last_status = None
    last_tool = None
    estimate_result = None
    rejected = []
    found_ids: set[str] = set()
    blocked_ids: set[str] = set()
    recorder.event(
        {
            "type": "plan_init",
            "decision_source": "model",
            "budget": budget,
            "deadline": case.get("deadline"),
            "available_hours": hours,
            "plan_ids": [plan["id"] for plan in plans],
        }
    )

    for _ in range(16):
        plan = plans[index] if plans and index < len(plans) else None
        current_id = None if plan is None else plan["id"]
        feasible_ids = [item["id"] for item in feasible_plans(plans, current_id, found_ids, blocked_ids)]
        estimate_ready = bool(plan and plan["id"] in estimate_done and estimate_result and estimate_result.get("ok"))
        within_budget = bool(estimate_result and estimate_result.get("within_budget")) if estimate_ready else False
        within_deadline = bool(estimate_result and estimate_result.get("within_deadline")) if estimate_ready else False
        blocked = bool(estimate_ready and not guard.allow_save(within_budget, within_deadline)) or last_status == "failed"
        observation = {
            "budget": budget,
            "deadline": case.get("deadline"),
            "current_plan_id": current_id,
            "remaining_plan_ids": feasible_ids,
            "feasible_plan_ids": feasible_ids,
            "last_tool": last_tool,
            "last_status": last_status,
            "estimate": None if not estimate_ready else estimate_result.get("estimate"),
            "within_budget": within_budget,
            "within_deadline": within_deadline,
            "estimate_ready": estimate_ready,
            "missing_fields": [],
            "blocked_continue": blocked,
            "succeeded_tools": [step["tool"] for step in recorder.steps if step["status"] == "success"],
        }
        action = decider.propose(observation)
        accepted, reject_reason = guard.review_action(action, observation)
        recorder.decision(
            action.get("action") or "stop",
            "model",
            action.get("reason") or "",
            proposed_by="model",
            accepted=accepted,
            to_plan=action.get("to_plan"),
            plan_id=action.get("plan_id"),
            observed_estimate=observation["estimate"],
            budget=budget,
        )
        if not accepted:
            recorder.decision("reject", "guard", reject_reason, proposed_action=action.get("action"), accepted=False)
            if action.get("error") or action.get("action") not in guard.ACTIONS:
                mark_not_run(recorder, ["plan_save"], reject_reason)
                return finish_incomplete(output, recorder, reject_reason, None, budget, "model")
            continue

        name = action["action"]
        if name == "stop":
            reason = action.get("reason") or "模型决定停止。方案未保存。"
            mark_not_run(recorder, ["plan_save"], reason)
            return finish_incomplete(output, recorder, reason, None, budget, "model")
        if name == "switch":
            target = action["to_plan"]
            if plan is not None:
                blocked_ids.add(plan["id"])
            index = next(pos for pos, item in enumerate(plans) if item["id"] == target)
            estimate_result = None
            last_status = None
            continue
        if name in {"save", "continue"} and estimate_ready and guard.allow_save(within_budget, within_deadline):
            saved = {
                "plan_id": plan["id"],
                "name": plan["name"],
                "theme": case["theme"],
                "materials": [item for item in plan["materials"] if item["id"] in found_ids],
                "script": plan["script"],
                "estimate": estimate_result["estimate"],
                "duration_hours": plan["duration_hours"],
                "budget": budget,
                "deadline": case["deadline"],
                "unit": UNIT,
                "rejected_plans": rejected,
            }
            save_result = invoke(
                "plan_save",
                {"saved": True, "plan_id": plan["id"], "estimate": saved["estimate"]},
                fail_tools,
                fail_once,
                runtime,
                plan_id=plan["id"],
                fail_plan_tools=fail_plan_tools,
            )
            if save_result.get("ok") is False:
                recorder.step("plan_save", "failed", f"保存{plan['name']}", {"plan_id": plan["id"]}, save_result, plan_id=plan["id"])
                reason = policy.save_failure_reason(save_result["message"])
                return finish_incomplete(output, recorder, reason, None, budget, "model")
            recorder.step("plan_save", "success", f"保存{plan['name']}", {"plan_id": plan["id"]}, save_result, plan_id=plan["id"])
            output["completed"] = True
            output["saved_plan"] = saved
            output["total_cost"] = saved["estimate"]
            output["incremental_cost"] = saved["estimate"]
            return finalize(output, recorder, budget, "model")
        if name == "save":
            reason = "守卫未允许保存。方案未保存。"
            return finish_incomplete(output, recorder, reason, None, budget, "model")

        if not search_done:
            result = invoke("material_search", search_body(plans), fail_tools, fail_once, runtime)
            status = "failed" if result.get("ok") is False else "success"
            recorder.step("material_search", status, TOOL_TITLES["material_search"], {"theme": case["theme"]}, result)
            last_tool, last_status = "material_search", status
            if status == "failed":
                reason = policy.tool_failure_reason(result["message"], search=True)
                mark_not_run(recorder, ["script_generate", "cost_estimate", "plan_save"], reason)
                return finish_incomplete(output, recorder, reason, None, budget, "model")
            found_ids = found_ids_from_search(result)
            search_done = True
            if not plans:
                reason = policy.empty_material_reason()
                mark_not_run(recorder, ["script_generate", "cost_estimate", "plan_save"], reason)
                return finish_incomplete(output, recorder, reason, {"missing": "materials"}, budget, "model")
            continue

        if plan["id"] not in script_done:
            result = invoke(
                "script_generate",
                {"plan_id": plan["id"], "script": plan["script"]},
                fail_tools,
                fail_once,
                runtime,
                plan_id=plan["id"],
                fail_plan_tools=fail_plan_tools,
            )
            status = "failed" if result.get("ok") is False else "success"
            request = {"plan_id": plan["id"], "theme": case["theme"], "material_ids": script_material_ids(plan, found_ids), "source": "material_search"}
            recorder.step("script_generate", status, f"生成{plan['name']}脚本", request, result, plan_id=plan["id"])
            last_tool, last_status = "script_generate", status
            if status == "failed":
                blocked_ids.add(plan["id"])
                if choose_next(plans, plan["id"], found_ids, blocked_ids) is None:
                    reason = policy.tool_failure_reason(result["message"])
                    mark_not_run(recorder, ["cost_estimate", "plan_save"], reason)
                    return finish_incomplete(output, recorder, reason, None, budget, "model")
                continue
            script_done.add(plan["id"])
            continue

        if plan["id"] not in estimate_done:
            usable = dict(plan)
            usable["materials"] = [item for item in plan["materials"] if item["id"] in found_ids]
            payload = estimate_payload(usable, budget, hours, UNIT)
            result = invoke(
                "cost_estimate",
                payload,
                fail_tools,
                fail_once,
                runtime,
                plan_id=plan["id"],
                fail_plan_tools=fail_plan_tools,
            )
            status = "failed" if result.get("ok") is False else "success"
            recorder.step("cost_estimate", status, f"估算{plan['name']}", {"plan_id": plan["id"]}, result, plan_id=plan["id"])
            last_tool, last_status = "cost_estimate", status
            if status == "failed":
                blocked_ids.add(plan["id"])
                if choose_next(plans, plan["id"], found_ids, blocked_ids) is None:
                    reason = policy.tool_failure_reason(result["message"])
                    mark_not_run(recorder, ["plan_save"], reason)
                    return finish_incomplete(output, recorder, reason, None, budget, "model")
                continue
            estimate_done.add(plan["id"])
            estimate_result = result
            if not result["within_budget"] or not result["within_deadline"]:
                rejected.append(
                    {
                        "plan_id": plan["id"],
                        "name": plan["name"],
                        "estimate": result["estimate"],
                        "over_by": result["over_by"],
                        "within_deadline": result["within_deadline"],
                    }
                )
            continue

        reason = "当前方案没有可继续的工具。方案未保存。"
        return finish_incomplete(output, recorder, reason, None, budget, "model")

    reason = "决策次数过多。方案未保存。"
    return finish_incomplete(output, recorder, reason, None, budget, "model")


def run_input(case: dict, store: dict | None = None, decider=None, persist: bool = False) -> tuple[dict, dict]:
    runs = int(case.get("runs", 1))
    memory: dict = {} if store is None else store
    if persist:
        loaded = load_state(case["case_id"])
        if loaded:
            memory.update(loaded)

    def once() -> tuple[dict, dict]:
        if decider is None:
            return run_once(case, memory)
        return run_model_once(case, memory, decider)

    if runs == 1:
        result = once()
        if persist:
            save_state(case["case_id"], memory)
        return result
    outputs = []
    traces = []
    for index in range(runs):
        output, trace = once()
        output["run"] = index + 1
        trace["run"] = index + 1
        outputs.append(output)
        traces.append(trace)
    first = outputs[0]
    second = outputs[-1]
    if case.get("resume"):
        check = {
            "run1_total_cost": first["total_cost"],
            "run2_total_cost": second["total_cost"],
            "run2_incremental_cost": second["incremental_cost"],
            "resumed": True,
            "reran_successful_steps": any(
                step["tool"] == "material_search" and step["status"] == "success" and step.get("executed_this_run")
                for step in second["step_status"]
            ),
            "double_counted": second["incremental_cost"] != second["total_cost"],
        }
    else:
        check = {
            "run1_total_cost": first["total_cost"],
            "run2_total_cost": second["total_cost"],
            "run2_incremental_cost": second["incremental_cost"],
            "double_counted": second["incremental_cost"] != 0 or second["total_cost"] != first["total_cost"],
        }
    result = (
        {"case_id": case["case_id"], "note": case.get("note"), "runs": outputs, "repeat_check": check},
        {"case_id": case["case_id"], "decision_source": traces[-1]["decision_source"], "runs": traces},
    )
    if persist:
        save_state(case["case_id"], memory)
    return result
