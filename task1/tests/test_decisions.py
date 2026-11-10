from __future__ import annotations

import json
from pathlib import Path

from scheduling_agent.agent import run_input, run_task
from scheduling_agent.model import ObservationDecisionModel
from scheduling_agent.store import DraftStore
from scheduling_agent.types import Observation


def names(trace: dict) -> list[str]:
    return [step["tool"] for step in trace["steps"]]


def test_model_source_has_no_material_script() -> None:
    text = Path("src/scheduling_agent/model.py").read_text(encoding="utf-8")
    for material_id in ("M01", "M02", "M03", "M04", "M10", "M11", "M12"):
        assert material_id not in text


def test_same_history_diverges_when_slot_result_changes() -> None:
    model = ObservationDecisionModel()
    request = {"material_id": "MX", "confirmed_slot": None}
    shared = [_read(), _rules_clear()]
    free = model.decide(request, shared + [_slot(preferred_free=True, alternative=None, free_slots=["18:00"])])
    busy = model.decide(
        request,
        shared + [_slot(preferred_free=False, alternative="19:00", free_slots=["19:00"], occupied_by="SCH-1800")],
    )
    assert free.tool == "save_draft" and free.arguments["commit"] is True
    assert free.arguments["suggested_slot"] == "18:00"
    assert busy.tool == "save_draft" and busy.arguments["commit"] is False
    assert busy.arguments["suggested_slot"] == "19:00"
    assert "待确认" in busy.rationale


def test_blocking_risk_ends_without_slot_lookup() -> None:
    decision = ObservationDecisionModel().decide(
        {"material_id": "MX"},
        [_read(), _rules_clear(blocking=True, risks=[{"reason": "承诺收益", "evidence": "保证收益"}])],
    )
    assert decision.kind == "finish"
    assert "阻断" in decision.rationale


def test_retryable_rule_failure_is_a_decision_not_a_blind_retry() -> None:
    model = ObservationDecisionModel()
    request = {"material_id": "MX"}
    once = model.decide(request, [_read(), _rule_failure(retryable=True)])
    twice = model.decide(request, [_read(), _rule_failure(retryable=True), _rule_failure(retryable=True)])
    permanent = model.decide(request, [_read(), _rule_failure(retryable=False)])
    assert once.tool == "check_rules" and "补查" in once.rationale
    assert twice.kind == "finish" and "阻断" in twice.rationale
    assert permanent.kind == "finish"


def test_missing_fields_lookup_then_block() -> None:
    model = ObservationDecisionModel()
    request = {"material_id": "MX"}
    first = model.decide(request, [_read(missing=["title"])])
    second = model.decide(request, [_read(missing=["title"]), _read(missing=["title"], refresh=True)])
    assert first.arguments["refresh"] is True and "补查" in first.rationale
    assert second.kind == "finish" and "阻断" in second.rationale


def test_user_confirmation_changes_the_save(workspace) -> None:
    data, store = workspace
    pending = run_task({"material_id": "M01"}, data_dir=data, store_path=store)
    confirmed = run_task(
        {"material_id": "M01", "confirmed_slot": "19:00"},
        data_dir=data,
        store_path=store.parent / "confirmed.json",
    )
    assert pending["result"]["outcome"] == "pending_confirmation"
    assert pending["result"]["committed_slot"] is None
    assert pending["result"]["hard_requirement_changed"] is False
    assert confirmed["result"]["outcome"] == "confirmed_draft"
    assert confirmed["result"]["committed_slot"] == "19:00"
    assert confirmed["result"]["change_authorized"] is True
    assert pending["trace"]["steps"][3]["arguments"]["commit"] is False
    assert confirmed["trace"]["steps"][3]["arguments"]["commit"] is True


def test_confirmed_slot_supersedes_pending_without_rewriting_it(workspace) -> None:
    data, store = workspace
    pending = run_task({"material_id": "M01"}, data_dir=data, store_path=store)["result"]
    confirmed = run_task(
        {"material_id": "M01", "confirmed_slot": "19:00"},
        data_dir=data,
        store_path=store,
    )["result"]
    repeated = run_task({"material_id": "M01"}, data_dir=data, store_path=store)["result"]
    old = _draft(store, pending["draft_id"])
    assert confirmed["outcome"] == "confirmed_draft"
    assert confirmed["committed_slot"] == "19:00"
    assert confirmed["change_authorized"] is True
    assert confirmed["publish_state"] == "not_published"
    assert confirmed["superseded_draft_ids"] == [pending["draft_id"]]
    assert confirmed["store_draft_count"] == 2
    assert old["confirmation_status"] == "superseded"
    assert old["review_status"] == "superseded"
    assert old["superseded_by"] == confirmed["draft_id"]
    assert old["requested_slot"] == "18:00"
    assert old["committed_slot"] is None
    assert old["hard_requirement_changed"] is False
    assert old["publish_state"] == "not_published"
    assert repeated["draft_save_status"] == "duplicate"
    assert repeated["outcome"] == "superseded"
    assert repeated["draft_id"] == pending["draft_id"]
    assert repeated["store_draft_count"] == 2
    assert "未新建" in repeated["message"]
    assert "已发布" not in repeated["message"]


def test_freeing_slot_supersedes_pending_suggestion(workspace) -> None:
    data, store = workspace
    pending = run_task({"material_id": "M01"}, data_dir=data, store_path=store)["result"]
    _write_slot(data, "18:00", occupied=False, occupied_by=None)
    freed = run_task({"material_id": "M01"}, data_dir=data, store_path=store)["result"]
    repeated = run_task({"material_id": "M01"}, data_dir=data, store_path=store)["result"]
    old = _draft(store, pending["draft_id"])
    assert freed["outcome"] == "scheduled_draft"
    assert freed["committed_slot"] == "18:00"
    assert freed["hard_requirement_changed"] is False
    assert freed["publish_state"] == "not_published"
    assert freed["superseded_draft_ids"] == [pending["draft_id"]]
    assert old["confirmation_status"] == "superseded"
    assert old["committed_slot"] is None
    assert old["hard_requirement_changed"] is False
    assert repeated["draft_save_status"] == "duplicate"
    assert repeated["draft_id"] == freed["draft_id"]
    assert repeated["store_draft_count"] == 2


def test_new_alternative_supersedes_previous_pending(workspace) -> None:
    data, store = workspace
    slots = json.loads((data / "slots.json").read_text(encoding="utf-8"))
    slots["2026-11-12"]["20:00"] = {"occupied": False, "occupied_by": None}
    (data / "slots.json").write_text(json.dumps(slots, ensure_ascii=False, indent=2), encoding="utf-8")
    first = run_task({"material_id": "M01"}, data_dir=data, store_path=store)["result"]
    _write_slot(data, "19:00", occupied=True, occupied_by="SCH-1900")
    second = run_task({"material_id": "M01"}, data_dir=data, store_path=store)["result"]
    old = _draft(store, first["draft_id"])
    assert first["suggested_slot"] == "19:00"
    assert second["suggested_slot"] == "20:00"
    assert second["confirmation_status"] == "pending"
    assert second["committed_slot"] is None
    assert second["hard_requirement_changed"] is False
    assert second["publish_state"] == "not_published"
    assert second["superseded_draft_ids"] == [first["draft_id"]]
    assert old["confirmation_status"] == "superseded"
    assert old["suggested_slot"] == "19:00"
    assert DraftStore(store).count() == 2


def test_failed_save_does_not_supersede_pending(workspace) -> None:
    data, store = workspace
    pending = run_task({"material_id": "M01"}, data_dir=data, store_path=store)["result"]
    faults = json.loads((data / "tool_faults.json").read_text(encoding="utf-8"))
    faults["save_draft"].append(
        {
            "material_id": "M01",
            "error": "storage_unavailable",
            "message": "草稿存储不可用",
            "retryable": False,
            "fail_count": 1,
        }
    )
    (data / "tool_faults.json").write_text(json.dumps(faults, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = run_task(
        {"material_id": "M01", "confirmed_slot": "19:00"},
        data_dir=data,
        store_path=store,
    )["result"]
    old = _draft(store, pending["draft_id"])
    assert failed["draft_save_status"] == "failed"
    assert failed["save_error"] == "storage_unavailable"
    assert failed["store_draft_count"] == 1
    assert "superseded_draft_ids" not in failed
    assert old["confirmation_status"] == "pending"
    assert "superseded_by" not in old
    assert old["publish_state"] == "not_published"


def test_other_material_does_not_supersede_pending(workspace) -> None:
    data, store = workspace
    pending = run_task({"material_id": "M01"}, data_dir=data, store_path=store)["result"]
    other = run_task({"material_id": "M10"}, data_dir=data, store_path=store)["result"]
    old = _draft(store, pending["draft_id"])
    assert other["outcome"] == "scheduled_draft"
    assert "superseded_draft_ids" not in other
    assert old["confirmation_status"] == "pending"
    assert DraftStore(store).count() == 2


def _draft(store: Path, draft_id: str) -> dict:
    found = DraftStore(store).find(draft_id)
    assert found is not None
    return found


def _write_slot(data: Path, slot: str, *, occupied: bool, occupied_by: str | None) -> None:
    path = data / "slots.json"
    slots = json.loads(path.read_text(encoding="utf-8"))
    slots["2026-11-12"][slot] = {"occupied": occupied, "occupied_by": occupied_by}
    path.write_text(json.dumps(slots, ensure_ascii=False, indent=2), encoding="utf-8")


def test_transient_failure_continues_and_permanent_failure_stops(workspace) -> None:
    data, store = workspace
    recovered = run_task({"material_id": "M12"}, data_dir=data, store_path=store)
    assert names(recovered["trace"]) == ["read_material", "check_rules", "check_rules", "query_slots", "save_draft"]
    assert recovered["trace"]["steps"][1]["result"]["ok"] is False
    assert recovered["trace"]["steps"][2]["result"]["ok"] is True
    assert recovered["result"]["draft_save_status"] == "saved"
    assert recovered["result"]["publish_state"] == "not_published"

    faults = json.loads((data / "tool_faults.json").read_text(encoding="utf-8"))
    faults["check_rules"] = [
        {
            "material_id": "M10",
            "error": "rule_index_missing",
            "message": "规则集缺失",
            "retryable": False,
            "fail_count": 5,
        }
    ]
    (data / "tool_faults.json").write_text(json.dumps(faults, ensure_ascii=False, indent=2), encoding="utf-8")
    blocked = run_task({"material_id": "M10"}, data_dir=data, store_path=store.parent / "blocked.json")
    assert names(blocked["trace"]) == ["read_material", "check_rules"]
    assert blocked["result"]["outcome"] == "tool_failure"
    assert blocked["result"]["draft_save_status"] == "not_saved"
    assert "补查" not in blocked["trace"]["final_decision"]["decision_basis"]


def test_freeing_occupied_slot_keeps_requested_time(workspace) -> None:
    data, store = workspace
    slots = json.loads((data / "slots.json").read_text(encoding="utf-8"))
    slots["2026-11-12"]["18:00"]["occupied"] = False
    slots["2026-11-12"]["18:00"]["occupied_by"] = None
    (data / "slots.json").write_text(json.dumps(slots, ensure_ascii=False, indent=2), encoding="utf-8")
    result = run_task({"material_id": "M01"}, data_dir=data, store_path=store)["result"]
    assert result["outcome"] == "scheduled_draft"
    assert result["committed_slot"] == "18:00"
    assert result["hard_requirement_changed"] is False
    assert result["confirmation_status"] == "not_required"
    assert result["publish_state"] == "not_published"


def test_no_alternative_waits_for_confirmation(workspace) -> None:
    data, store = workspace
    slots = json.loads((data / "slots.json").read_text(encoding="utf-8"))
    slots["2026-11-12"]["19:00"]["occupied"] = True
    slots["2026-11-12"]["19:00"]["occupied_by"] = "SCH-1900"
    (data / "slots.json").write_text(json.dumps(slots, ensure_ascii=False, indent=2), encoding="utf-8")
    result = run_task({"material_id": "M01"}, data_dir=data, store_path=store)["result"]
    assert result["outcome"] == "pending_confirmation"
    assert result["suggested_slot"] is None
    assert result["draft_save_status"] == "not_saved"
    assert result["store_draft_count"] == 0
    assert "没有可用替代时段" in result["pending_confirmations"][0]


def test_supplement_then_schedules(workspace) -> None:
    data, store = workspace
    supplements = {
        "M02": {
            "title": "午间菜谱",
            "body": "今日供应番茄鸡蛋面。",
            "audience": "staff",
        }
    }
    (data / "supplements.json").write_text(json.dumps(supplements, ensure_ascii=False, indent=2), encoding="utf-8")
    bundle = run_task({"material_id": "M02"}, data_dir=data, store_path=store)
    assert names(bundle["trace"])[0:2] == ["read_material", "read_material"]
    assert bundle["trace"]["steps"][0]["result"]["complete"] is False
    assert bundle["trace"]["steps"][1]["result"]["complete"] is True
    assert bundle["result"]["outcome"] == "scheduled_draft"
    assert bundle["result"]["publish_state"] == "not_published"


def test_agent_loop_does_not_retry_unless_the_model_asks(workspace) -> None:
    data, store = workspace

    class Once:
        def __init__(self) -> None:
            self.calls = 0

        def decide(self, request, observations):
            self.calls += 1
            if observations:
                from scheduling_agent.types import Decision

                return Decision(kind="finish", rationale="只调用一次后结束。")
            from scheduling_agent.types import Decision

            return Decision(
                kind="tool",
                tool="check_rules",
                arguments={"material_id": request["material_id"]},
                rationale="只检查一次规则。",
            )

    model = Once()
    bundle = run_task({"material_id": "M10"}, data_dir=data, store_path=store, model=model)
    assert names(bundle["trace"]) == ["check_rules"]
    assert model.calls == 2


def _read(missing: list[str] | None = None, refresh: bool = False) -> Observation:
    material = {
        "id": "MX",
        "title": "标题",
        "body": "正文",
        "channel": "app_push",
        "audience": "members",
        "requested_slot": "18:00",
        "date": "2026-11-12",
        "hard_requirement": True,
        "content_revision": "r1",
        "queue_status": "pending",
    }
    return Observation(
        step=1,
        tool="read_material",
        arguments={"material_id": "MX", "refresh": refresh},
        ok=True,
        summary="读取",
        payload={"ok": True, "material": material, "missing_fields": missing or [], "complete": not missing},
    )


def _rules_clear(blocking: bool = False, risks: list | None = None) -> Observation:
    return Observation(
        step=2,
        tool="check_rules",
        arguments={"material_id": "MX"},
        ok=True,
        summary="规则",
        payload={"ok": True, "blocking": blocking, "risks": risks or []},
    )


def _rule_failure(retryable: bool) -> Observation:
    return Observation(
        step=2,
        tool="check_rules",
        arguments={"material_id": "MX"},
        ok=False,
        summary="失败",
        payload={"ok": False, "error": "rule_service_timeout", "retryable": retryable},
    )


def _slot(*, preferred_free: bool, alternative: str | None, free_slots: list[str], occupied_by: str | None = None) -> Observation:
    return Observation(
        step=3,
        tool="query_slots",
        arguments={"date": "2026-11-12", "slot": "18:00"},
        ok=True,
        summary="时段",
        payload={
            "ok": True,
            "preferred_free": preferred_free,
            "alternative": alternative,
            "free_slots": free_slots,
            "occupied_by": occupied_by,
        },
    )
