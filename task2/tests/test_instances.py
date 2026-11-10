"""检查实例是否符合参考实例和验收规则。"""

import json
import unittest
from pathlib import Path

from src.agent.planner import ROOT, run_input

EXAMPLES = ROOT / "examples"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def tool_events(trace: dict, tool: str) -> list[dict]:
    return [event for event in trace["events"] if event["type"] == "tool" and event["tool"] == tool]


class InstanceTests(unittest.TestCase):
    def test_stored_outputs_match_rerun(self) -> None:
        for case_dir in sorted(path for path in EXAMPLES.iterdir() if (path / "input.json").exists()):
            case = read_json(case_dir / "input.json")
            output, trace = run_input(case)
            self.assertEqual(output, read_json(case_dir / "output.json"))
            self.assertEqual(trace, read_json(case_dir / "trace.json"))

    def test_reference_switches_from_12_to_8(self) -> None:
        case = read_json(EXAMPLES / "over_budget_switch" / "input.json")
        output, trace = run_input(case)
        estimates = tool_events(trace, "cost_estimate")
        self.assertEqual([item["result"]["estimate"] for item in estimates], [12, 8])
        switch = next(item for item in output["decisions"] if item["action"] == "switch")
        self.assertEqual(switch["observed_estimate"], 12)
        self.assertEqual(switch["budget"], 10)
        self.assertEqual(switch["to_plan"], "alternative")
        self.assertLess(switch["seq"], estimates[1]["seq"])
        save = next(item for item in output["decisions"] if item["action"] == "save")
        self.assertGreater(save["seq"], estimates[1]["seq"])
        self.assertTrue(output["completed"])
        self.assertEqual(output["saved_plan"]["plan_id"], "alternative")
        self.assertEqual(output["saved_plan"]["estimate"], 8)
        self.assertEqual(output["total_cost"], 8)
        self.assertLessEqual(output["total_cost"], output["budget"])

    def test_no_feasible_returns_gap(self) -> None:
        output = read_json(EXAMPLES / "no_feasible" / "output.json")
        self.assertFalse(output["completed"])
        self.assertIsNone(output["saved_plan"])
        self.assertEqual(output["gap"]["budget"], 10)
        self.assertEqual(output["gap"]["lowest_estimate"], 12)
        self.assertEqual(output["gap"]["shortfall"], 2)
        self.assertIn("缺口 2", output["incomplete_reason"])
        save_steps = [step for step in output["step_status"] if step["tool"] == "plan_save"]
        self.assertTrue(save_steps)
        self.assertNotEqual(save_steps[-1]["status"], "success")

    def test_failed_steps_are_not_success(self) -> None:
        for case_dir in sorted(path for path in EXAMPLES.iterdir() if (path / "output.json").exists()):
            output = read_json(case_dir / "output.json")
            runs = output["runs"] if "runs" in output else [output]
            for run in runs:
                self.assertFalse(run["failed_steps_marked_success"])
                status_by_id = {step["id"]: step["status"] for step in run["step_status"]}
                for item in run["tool_results"]:
                    result = item.get("result")
                    if isinstance(result, dict) and result.get("ok") is False:
                        self.assertEqual(status_by_id[item["id"]], "failed")
                        self.assertEqual(item["status"], "failed")

    def test_tool_failure_keeps_prior_success(self) -> None:
        output = read_json(EXAMPLES / "tool_failure" / "output.json")
        self.assertFalse(output["completed"])
        self.assertIsNone(output["saved_plan"])
        statuses = {step["tool"]: step["status"] for step in output["step_status"]}
        self.assertEqual(statuses["material_search"], "success")
        self.assertEqual(statuses["script_generate"], "failed")
        self.assertEqual(statuses["cost_estimate"], "not_run")
        self.assertEqual(statuses["plan_save"], "not_run")
        search = next(step for step in output["step_status"] if step["tool"] == "material_search")
        self.assertEqual(search["status"], "success")

    def test_missing_budget_is_not_invented(self) -> None:
        output = read_json(EXAMPLES / "missing_info" / "output.json")
        self.assertIsNone(output["budget"])
        self.assertFalse(output["completed"])
        self.assertIsNone(output["saved_plan"])
        self.assertEqual(output["gap"]["missing_fields"], ["预算"])
        self.assertIn("缺少预算", output["incomplete_reason"])
        self.assertTrue(all(step["status"] == "not_run" for step in output["step_status"]))

    def test_insufficient_materials(self) -> None:
        output = read_json(EXAMPLES / "insufficient_materials" / "output.json")
        self.assertFalse(output["completed"])
        self.assertIsNone(output["saved_plan"])
        self.assertIn("无可用素材", output["incomplete_reason"])
        self.assertEqual(output["step_status"][0]["status"], "success")
        self.assertTrue(all(step["status"] == "not_run" for step in output["step_status"][1:]))

    def test_normal_saves_within_budget(self) -> None:
        output = read_json(EXAMPLES / "normal" / "output.json")
        trace = read_json(EXAMPLES / "normal" / "trace.json")
        self.assertTrue(output["completed"])
        self.assertEqual(output["total_cost"], 8)
        self.assertLessEqual(output["total_cost"], output["budget"])
        self.assertFalse(any(event["action"] == "switch" for event in trace["events"] if event["type"] == "decision"))

    def test_repeat_does_not_double_charge(self) -> None:
        output = read_json(EXAMPLES / "repeat" / "output.json")
        self.assertEqual(len(output["runs"]), 2)
        self.assertEqual(output["runs"][0]["total_cost"], 8)
        self.assertEqual(output["runs"][1]["total_cost"], 8)
        self.assertEqual(output["runs"][1]["incremental_cost"], 0)
        self.assertTrue(output["runs"][1]["reused"])
        self.assertFalse(output["repeat_check"]["double_counted"])
        self.assertTrue(all(step["status"] == "skipped" for step in output["runs"][1]["step_status"]))
        self.assertTrue(all(step["prior_status"] == "success" for step in output["runs"][1]["step_status"]))


if __name__ == "__main__":
    unittest.main()
