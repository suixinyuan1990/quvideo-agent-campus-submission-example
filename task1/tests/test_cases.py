from __future__ import annotations

from scheduling_agent.agent import run_input, run_task

from test_decisions import names


def test_normal_schedule_saves_one_draft(workspace) -> None:
    data, store = workspace
    result = run_task({"material_id": "M10"}, data_dir=data, store_path=store)["result"]
    assert result["run_status"] == "completed"
    assert result["outcome"] == "scheduled_draft"
    assert result["review_status"] == "ready_draft"
    assert result["risk_reasons"] == []
    assert result["requested_slot"] == "10:00"
    assert result["suggested_slot"] == "10:00"
    assert result["committed_slot"] == "10:00"
    assert result["pending_confirmations"] == []
    assert result["draft_save_status"] == "saved"
    assert result["draft_id"].startswith("D-")
    assert result["publish_state"] == "not_published"
    assert result["hard_requirement_changed"] is False
    assert result["store_draft_count"] == 1
    assert result["saved_draft"]["publish_state"] == "not_published"
    assert "未发布" in result["message"]
    assert "已发布" not in result["message"]


def test_missing_information_blocks_schedule(workspace) -> None:
    data, store = workspace
    bundle = run_task({"material_id": "M02"}, data_dir=data, store_path=store)
    result = bundle["result"]
    assert names(bundle["trace"]) == ["read_material", "read_material"]
    assert "补查" in bundle["trace"]["steps"][1]["decision_basis"]
    assert result["outcome"] == "insufficient_information"
    assert result["draft_save_status"] == "not_saved"
    assert result["store_draft_count"] == 0
    assert result["suggested_slot"] is None
    assert "标题" in result["pending_confirmations"][0]
    assert "正文" in result["pending_confirmations"][0]
    assert "受众" in result["pending_confirmations"][0]
    assert result["publish_state"] == "not_published"


def test_rule_risk_blocks_before_scheduling(workspace) -> None:
    data, store = workspace
    bundle = run_task({"material_id": "M03"}, data_dir=data, store_path=store)
    result = bundle["result"]
    assert names(bundle["trace"]) == ["read_material", "check_rules"]
    assert result["outcome"] == "blocked_by_rule"
    assert result["review_status"] == "blocked"
    assert any("承诺收益" in item for item in result["risk_reasons"])
    assert any("绝对化承诺" in item for item in result["risk_reasons"])
    assert any("诱导立即交易" in item for item in result["risk_reasons"])
    assert result["draft_save_status"] == "not_saved"
    assert result["store_draft_count"] == 0
    assert result["publish_state"] == "not_published"


def test_slot_conflict_suggests_alternative_without_rewriting_requirement(workspace) -> None:
    data, store = workspace
    bundle = run_task({"material_id": "M01"}, data_dir=data, store_path=store)
    result = bundle["result"]
    assert names(bundle["trace"]) == ["read_material", "check_rules", "query_slots", "save_draft"]
    assert result["outcome"] == "pending_confirmation"
    assert result["requested_slot"] == "18:00"
    assert result["suggested_slot"] == "19:00"
    assert result["committed_slot"] is None
    assert result["hard_requirement"] is True
    assert result["hard_requirement_changed"] is False
    assert result["confirmation_status"] == "pending"
    assert result["draft_save_status"] == "saved"
    assert result["publish_state"] == "not_published"
    assert "未经确认" in result["pending_confirmations"][0]
    assert "19:00" in result["pending_confirmations"][0]
    assert "待确认" in bundle["trace"]["steps"][3]["decision_basis"]
    assert result["saved_draft"]["publish_state"] == "not_published"


def test_duplicate_submit_keeps_a_single_draft(workspace) -> None:
    data, store = workspace
    bundle = run_input({"material_id": "M01", "repeat": 2}, data_dir=data, store_path=store)
    first, second = bundle["output"]["runs"]
    assert bundle["output"]["store_draft_count"] == 1
    assert len(bundle["output"]["drafts"]) == 1
    assert first["draft_save_status"] == "saved"
    assert second["draft_save_status"] == "duplicate"
    assert first["draft_id"] == second["draft_id"]
    assert second["publish_state"] == "not_published"
    assert "未新建" in second["message"]
    assert "已经存在" in bundle["trace"]["runs"][1]["final_decision"]["decision_basis"]


def test_save_failure_is_explicit(workspace) -> None:
    data, store = workspace
    bundle = run_task({"material_id": "M04"}, data_dir=data, store_path=store)
    result = bundle["result"]
    assert names(bundle["trace"]) == ["read_material", "check_rules", "query_slots", "save_draft"]
    assert result["run_status"] == "completed"
    assert result["outcome"] == "save_failed"
    assert result["draft_save_status"] == "failed"
    assert result["save_error"] == "storage_unavailable"
    assert result["draft_id"] is None
    assert result["saved_draft"] is None
    assert result["store_draft_count"] == 0
    assert result["publish_state"] == "not_published"
    assert "保存失败" in result["message"]
    assert "已发布" not in result["message"]


def test_tool_failure_does_not_treat_material_as_clean(workspace) -> None:
    data, store = workspace
    bundle = run_task({"material_id": "M11"}, data_dir=data, store_path=store)
    result = bundle["result"]
    assert names(bundle["trace"]) == ["read_material", "check_rules", "check_rules"]
    assert bundle["trace"]["steps"][1]["result"]["ok"] is False
    assert bundle["trace"]["steps"][2]["result"]["ok"] is False
    assert "补查" in bundle["trace"]["steps"][2]["decision_basis"]
    assert "query_slots" not in names(bundle["trace"])
    assert result["outcome"] == "tool_failure"
    assert result["tool_error"] == "rule_service_timeout"
    assert result["risk_reasons"] == []
    assert result["draft_save_status"] == "not_saved"
    assert result["publish_state"] == "not_published"


def test_unknown_material(workspace) -> None:
    data, store = workspace
    result = run_task({"material_id": "M99"}, data_dir=data, store_path=store)["result"]
    assert result["outcome"] == "insufficient_information"
    assert result["draft_save_status"] == "not_saved"
    assert result["publish_state"] == "not_published"
