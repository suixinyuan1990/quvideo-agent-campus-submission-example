"""守卫、部分成功、失败续跑和模型动作解析。"""

import json
import unittest
from pathlib import Path

from src.agent.guard import review_action
from src.agent.model import parse_model_response
from src.agent.orchestrator import run_input

ROOT = Path(__file__).resolve().parents[1]


class ScriptedDecider:
    source = "model"

    def __init__(self, actions: list[dict]) -> None:
        self.actions = list(actions)

    def propose(self, observation: dict) -> dict:
        if not self.actions:
            return {"action": "stop", "reason": "没有更多动作", "error": True}
        return self.actions.pop(0)


def reference_case() -> dict:
    return {
        "case_id": "model_guard",
        "theme": "春季新品上新",
        "budget": 10,
        "deadline": "2026-11-20",
        "as_of": "2026-11-10T09:00:00",
        "plan_set": "reference",
    }


class GuardTests(unittest.TestCase):
    def test_over_budget_save_is_rejected(self) -> None:
        accepted, reason = review_action(
            {"action": "save", "plan_id": "initial"},
            {
                "estimate_ready": True,
                "within_budget": False,
                "within_deadline": True,
                "estimate": 12,
                "budget": 10,
                "remaining_plan_ids": ["alternative"],
            },
        )
        self.assertFalse(accepted)
        self.assertIn("拒绝保存", reason)

    def test_scripted_model_cannot_save_the_12_plan(self) -> None:
        decider = ScriptedDecider(
            [
                {"action": "continue", "reason": "检索素材"},
                {"action": "continue", "reason": "生成初始脚本"},
                {"action": "continue", "reason": "估算初始方案"},
                {"action": "save", "plan_id": "initial", "reason": "保存初始方案"},
                {"action": "switch", "to_plan": "alternative", "reason": "改选替代方案"},
                {"action": "continue", "reason": "生成替代脚本"},
                {"action": "continue", "reason": "估算替代方案"},
                {"action": "save", "plan_id": "alternative", "reason": "保存替代方案"},
            ]
        )
        output, trace = run_input(reference_case(), decider=decider)
        self.assertEqual(trace["decision_source"], "model")
        rejected = [item for item in output["decisions"] if item["action"] == "save" and item.get("accepted") is False]
        self.assertTrue(rejected)
        self.assertEqual(rejected[0]["observed_estimate"], 12)
        self.assertTrue(any(item["action"] == "reject" and item["rule"] == "guard" for item in output["decisions"]))
        self.assertTrue(output["completed"])
        self.assertEqual(output["saved_plan"]["estimate"], 8)
        self.assertEqual(output["total_cost"], 8)
        self.assertFalse(output["failed_steps_marked_success"])

    def test_unparsed_action_does_not_save(self) -> None:
        output, _trace = run_input(reference_case(), decider=ScriptedDecider([{"action": "dance", "reason": "看不懂"}]))
        self.assertFalse(output["completed"])
        self.assertIsNone(output["saved_plan"])
        self.assertFalse(output["failed_steps_marked_success"])

    def test_parse_tool_call(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "arguments": json.dumps(
                                        {"action": "switch", "to_plan": "alternative", "reason": "超过预算"},
                                        ensure_ascii=False,
                                    )
                                }
                            }
                        ]
                    }
                }
            ]
        }
        action = parse_model_response(payload)
        self.assertEqual(action["action"], "switch")
        self.assertEqual(action["to_plan"], "alternative")


class ExtraInstanceTests(unittest.TestCase):
    def test_partial_materials_keep_what_was_found(self) -> None:
        case = json.loads((ROOT / "examples" / "partial_materials" / "input.json").read_text(encoding="utf-8"))
        output, trace = run_input(case)
        search = next(event for event in trace["events"] if event["type"] == "tool" and event["tool"] == "material_search")
        self.assertEqual(search["status"], "success")
        self.assertTrue(search["result"]["partial"])
        self.assertIn("详情页", search["result"]["missing"])
        switch = next(item for item in output["decisions"] if item["action"] == "switch")
        self.assertEqual(switch["to_plan"], "alternative")
        self.assertIn("详情页", switch["missing_materials"])
        self.assertTrue(output["completed"])
        self.assertEqual(output["total_cost"], 8)
        self.assertEqual(output["saved_plan"]["plan_id"], "alternative")

    def test_resume_does_not_rerun_success_or_mark_failure_as_success(self) -> None:
        case = json.loads((ROOT / "examples" / "resume_failed" / "input.json").read_text(encoding="utf-8"))
        output, _trace = run_input(case)
        first, second = output["runs"]
        self.assertFalse(first["completed"])
        self.assertEqual(next(step["status"] for step in first["step_status"] if step["tool"] == "script_generate"), "failed")
        self.assertEqual(next(step["status"] for step in first["step_status"] if step["tool"] == "material_search"), "success")
        self.assertEqual(first["total_cost"], 0)
        search = next(step for step in second["step_status"] if step["tool"] == "material_search")
        self.assertEqual(search["status"], "skipped")
        self.assertEqual(search["prior_status"], "success")
        self.assertFalse(search["executed_this_run"])
        self.assertEqual(next(step["status"] for step in second["step_status"] if step["tool"] == "script_generate"), "success")
        self.assertTrue(second["completed"])
        self.assertEqual(second["total_cost"], 8)
        self.assertEqual(second["incremental_cost"], 8)
        self.assertFalse(output["repeat_check"]["double_counted"])
        self.assertFalse(output["repeat_check"]["reran_successful_steps"])
        self.assertFalse(second["failed_steps_marked_success"])


if __name__ == "__main__":
    unittest.main()
