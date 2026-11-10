from __future__ import annotations

from scheduling_agent.agent import run_task
from scheduling_agent.types import Decision


class Forever:
    def decide(self, request, observations):
        return Decision(
            kind="tool",
            tool="read_material",
            arguments={"material_id": request["material_id"], "refresh": False},
            rationale="测试替身继续读取，用来验证上限。",
        )


def test_step_limit_returns_incomplete(workspace) -> None:
    data, store = workspace
    bundle = run_task({"material_id": "M10", "max_steps": 2}, data_dir=data, store_path=store)
    result = bundle["result"]
    assert result["run_status"] == "incomplete"
    assert result["outcome"] == "incomplete"
    assert result["review_status"] == "incomplete"
    assert result["incomplete_reason"] == "已达到执行步数上限（2），任务未完成"
    assert result["draft_save_status"] == "not_saved"
    assert result["publish_state"] == "not_published"
    assert result["limits"]["hit_limit"] is True
    assert result["limits"]["decision_count"] == 2
    assert bundle["trace"]["stopped"]["reason"] == "max_steps"
    assert len(bundle["trace"]["steps"]) == 2


def test_tool_call_limit_records_the_blocked_action(workspace) -> None:
    data, store = workspace
    bundle = run_task({"material_id": "M10", "max_tool_calls": 2}, data_dir=data, store_path=store)
    result = bundle["result"]
    assert result["run_status"] == "incomplete"
    assert result["incomplete_reason"] == "已达到工具调用次数上限（2），任务未完成"
    assert result["limits"]["tool_calls_used"] == 2
    assert bundle["trace"]["stopped"]["attempted_action"] == "query_slots"
    assert bundle["trace"]["stopped"]["executed"] is False
    assert bundle["trace"]["steps"][-1]["next_action"] == "query_slots"
    assert result["draft_save_status"] == "not_saved"
    assert result["publish_state"] == "not_published"


def test_limit_holds_when_model_never_finishes(workspace) -> None:
    data, store = workspace
    result = run_task(
        {"material_id": "M10"},
        data_dir=data,
        store_path=store,
        model=Forever(),
        max_tool_calls=3,
        max_steps=8,
    )["result"]
    assert result["run_status"] == "incomplete"
    assert result["limits"]["tool_calls_used"] == 3
    assert "未完成" in result["incomplete_reason"]
    assert result["publish_state"] == "not_published"
    assert result["draft_save_status"] == "not_saved"
    assert result["store_draft_count"] == 0
