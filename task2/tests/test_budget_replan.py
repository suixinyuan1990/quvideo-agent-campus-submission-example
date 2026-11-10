"""核对预算、步骤依赖，以及失败后是否重规划并保留成功结果。"""

import json
import unittest
from pathlib import Path

from src.agent.orchestrator import run_input

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def estimates(trace: dict) -> list[dict]:
    return [event["result"] for event in trace["events"] if event["type"] == "tool" and event["tool"] == "cost_estimate" and event["status"] == "success"]


class BudgetAndReplanTests(unittest.TestCase):
    def test_reference_budget_matches_breakdown_and_does_not_add_rejected_plan(self) -> None:
        case = read_json(EXAMPLES / "over_budget_switch" / "input.json")
        output, trace = run_input(case)
        rows = estimates(trace)
        self.assertEqual([row["estimate"] for row in rows], [12, 8])
        for row in rows:
            self.assertEqual(row["material_cost"] + row["script_cost"], row["estimate"])
            self.assertEqual(row["over_by"], max(0, row["estimate"] - row["budget"]))
        self.assertEqual(output["budget"], 10)
        self.assertGreater(rows[0]["estimate"], output["budget"])
        self.assertLessEqual(rows[1]["estimate"], output["budget"])
        self.assertEqual(output["total_cost"], 8)
        self.assertEqual(output["saved_plan"]["estimate"], 8)
        self.assertNotEqual(output["total_cost"], 12 + 8)
        self.assertEqual(output["saved_plan"]["rejected_plans"][0]["estimate"], 12)

    def test_no_feasible_gap_is_lowest_minus_budget(self) -> None:
        case = read_json(EXAMPLES / "no_feasible" / "input.json")
        output, trace = run_input(case)
        rows = estimates(trace)
        self.assertEqual([row["estimate"] for row in rows], [12, 15])
        lowest = min(row["estimate"] for row in rows)
        self.assertEqual(output["gap"]["shortfall"], lowest - output["budget"])
        self.assertEqual(output["gap"]["shortfall"], 2)
        self.assertEqual(output["total_cost"], 0)
        self.assertIsNone(output["saved_plan"])

    def test_injected_script_failure_replans_and_keeps_search(self) -> None:
        case = read_json(EXAMPLES / "replan_after_failure" / "input.json")
        output, trace = run_input(case)
        steps = output["step_status"]
        search = next(step for step in steps if step["tool"] == "material_search")
        failed_script = next(step for step in steps if step["tool"] == "script_generate" and step["plan_id"] == "initial")
        self.assertEqual(search["status"], "success")
        self.assertEqual(failed_script["status"], "failed")
        self.assertFalse(any(step["tool"] == "cost_estimate" and step["plan_id"] == "initial" for step in steps))
        self.assertFalse(any(step["tool"] == "plan_save" and step["plan_id"] == "initial" and step["status"] == "success" for step in steps))
        switch = next(item for item in output["decisions"] if item["action"] == "switch")
        self.assertEqual(switch["rule"], "R3")
        self.assertEqual(switch["from_plan"], "initial")
        self.assertEqual(switch["to_plan"], "alternative")
        self.assertEqual(switch["retained"], ["material_search"])
        self.assertLess(search["id"], failed_script["id"])
        alt_estimate = next(row for row in estimates(trace) if row["plan_id"] == "alternative")
        self.assertEqual(alt_estimate["material_cost"] + alt_estimate["script_cost"], 8)
        self.assertLessEqual(alt_estimate["estimate"], output["budget"])
        self.assertEqual(output["total_cost"], 8)
        self.assertEqual(output["saved_plan"]["plan_id"], "alternative")
        self.assertTrue(output["completed"])
        failed_results = [
            item for item in output["tool_results"]
            if isinstance(item.get("result"), dict) and item["result"].get("ok") is False
        ]
        self.assertTrue(failed_results)
        self.assertTrue(all(item["status"] == "failed" for item in failed_results))
        search_result = next(item for item in output["tool_results"] if item["tool"] == "material_search")
        self.assertEqual(search_result["status"], "success")
        self.assertGreater(search_result["result"]["count"], 0)


if __name__ == "__main__":
    unittest.main()
