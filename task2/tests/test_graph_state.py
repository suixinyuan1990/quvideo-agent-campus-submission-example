"""依赖图、检索结果传递、按预算选择，以及磁盘状态。"""

import json
import unittest
from pathlib import Path

from src.agent.disk_state import clear_state
from src.agent.graph import DEPENDENCIES, choose_next
from src.agent.orchestrator import run_input

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class GraphStateTests(unittest.TestCase):
    def test_dependencies_are_explicit(self) -> None:
        self.assertEqual(DEPENDENCIES["script_generate"], ["material_search"])
        self.assertEqual(DEPENDENCIES["cost_estimate"], ["script_generate"])
        self.assertEqual(DEPENDENCIES["plan_save"], ["cost_estimate"])

    def test_script_reads_search_result_ids(self) -> None:
        case = read_json(EXAMPLES / "partial_materials" / "input.json")
        _output, trace = run_input(case)
        search = next(event for event in trace["events"] if event["type"] == "tool" and event["tool"] == "material_search")
        found = {item["id"] for item in search["result"]["materials"]}
        self.assertNotIn("m-detail", found)
        scripts = [event for event in trace["events"] if event["type"] == "tool" and event["tool"] == "script_generate" and event["status"] == "success"]
        self.assertTrue(scripts)
        for event in scripts:
            self.assertEqual(event["request"]["source"], "material_search")
            self.assertTrue(set(event["request"]["material_ids"]).issubset(found))

    def test_over_budget_picks_lowest_feasible_not_list_order(self) -> None:
        case = read_json(EXAMPLES / "choose_feasible" / "input.json")
        output, trace = run_input(case)
        estimated = [event["result"]["plan_id"] for event in trace["events"] if event["type"] == "tool" and event["tool"] == "cost_estimate"]
        self.assertEqual(estimated, ["initial", "lean"])
        self.assertNotIn("pricey", estimated)
        switch = next(item for item in output["decisions"] if item["action"] == "switch")
        self.assertEqual(switch["to_plan"], "lean")
        self.assertEqual(switch["reason_code"], "budget")
        self.assertEqual(output["total_cost"], 6)
        self.assertEqual(output["saved_plan"]["plan_id"], "lean")
        self.assertLessEqual(output["total_cost"], output["budget"])

    def test_choose_next_orders_by_estimate(self) -> None:
        plans = [
            {"id": "pricey", "estimate": 15, "materials": [{"id": "a"}]},
            {"id": "lean", "estimate": 6, "materials": [{"id": "b"}]},
        ]
        chosen = choose_next(plans, "initial", {"a", "b"}, set())
        self.assertEqual(chosen["id"], "lean")

    def test_disk_second_command_reuses_saved_plan(self) -> None:
        case = read_json(EXAMPLES / "normal" / "input.json")
        case = dict(case)
        case["case_id"] = "disk_repeat"
        clear_state(case["case_id"])
        try:
            first, _trace = run_input(case, persist=True)
            second, _trace = run_input(case, persist=True)
        finally:
            clear_state(case["case_id"])
        self.assertTrue(first["completed"])
        self.assertEqual(first["total_cost"], 8)
        self.assertTrue(second["reused"])
        self.assertEqual(second["incremental_cost"], 0)
        self.assertEqual(second["total_cost"], 8)
        self.assertTrue(all(step["status"] == "skipped" for step in second["step_status"]))

    def test_disk_resume_retries_only_failed_step(self) -> None:
        case = read_json(EXAMPLES / "resume_failed" / "input.json")
        case = dict(case)
        case["case_id"] = "disk_resume"
        case["runs"] = 1
        clear_state(case["case_id"])
        try:
            first, _trace = run_input(case, persist=True)
            second, _trace = run_input(case, persist=True)
        finally:
            clear_state(case["case_id"])
        self.assertFalse(first["completed"])
        self.assertEqual(next(step["status"] for step in first["step_status"] if step["tool"] == "script_generate"), "failed")
        search = next(step for step in second["step_status"] if step["tool"] == "material_search")
        self.assertEqual(search["status"], "skipped")
        self.assertFalse(search["executed_this_run"])
        self.assertEqual(next(step["status"] for step in second["step_status"] if step["tool"] == "script_generate"), "success")
        self.assertEqual(second["total_cost"], 8)

    def test_model_can_switch_after_tool_failure(self) -> None:
        from tests.test_guard_resume import ScriptedDecider

        case = read_json(EXAMPLES / "replan_after_failure" / "input.json")
        case = dict(case)
        case["case_id"] = "model_replan"
        decider = ScriptedDecider(
            [
                {"action": "continue", "reason": "检索素材"},
                {"action": "continue", "reason": "生成初始脚本"},
                {"action": "switch", "to_plan": "alternative", "reason": "脚本失败，改选替代方案"},
                {"action": "continue", "reason": "生成替代脚本"},
                {"action": "continue", "reason": "估算替代方案"},
                {"action": "save", "plan_id": "alternative", "reason": "保存替代方案"},
            ]
        )
        output, trace = run_input(case, decider=decider)
        self.assertEqual(trace["decision_source"], "model")
        failed = [step for step in output["step_status"] if step["tool"] == "script_generate" and step["plan_id"] == "initial"]
        self.assertEqual(failed[0]["status"], "failed")
        self.assertEqual(next(step["status"] for step in output["step_status"] if step["tool"] == "material_search"), "success")
        self.assertFalse(any(step["tool"] == "cost_estimate" and step["plan_id"] == "initial" for step in output["step_status"]))
        self.assertEqual(output["saved_plan"]["plan_id"], "alternative")
        self.assertEqual(output["total_cost"], 8)


if __name__ == "__main__":
    unittest.main()
