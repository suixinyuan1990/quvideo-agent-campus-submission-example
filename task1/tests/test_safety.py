from __future__ import annotations

import json

import pytest

from scheduling_agent.catalog import DataCatalog
from scheduling_agent.model import parse_decision
from scheduling_agent.store import DraftStore
from scheduling_agent.tools import Toolset
from scheduling_agent.types import ModelOutputError


def _tools(workspace, confirmed=None) -> Toolset:
    data, store = workspace
    return Toolset(DataCatalog(data), DraftStore(store), confirmed)


def test_publish_flag_is_rejected(workspace) -> None:
    result = _tools(workspace).call(
        "save_draft",
        {
            "material_id": "M10",
            "suggested_slot": "10:00",
            "commit": True,
            "publish": True,
        },
    )
    assert result["ok"] is False
    assert result["error"] == "publish_forbidden"
    assert DraftStore(workspace[1]).count() == 0


def test_model_cannot_invent_confirmation(workspace) -> None:
    invented = _tools(workspace, confirmed=None).call(
        "save_draft",
        {
            "material_id": "M01",
            "suggested_slot": "19:00",
            "commit": True,
            "confirmed_slot": "19:00",
        },
    )
    assert invented["ok"] is False
    assert invented["error"] == "confirmation_mismatch"
    locked = _tools(workspace, confirmed=None).call(
        "save_draft",
        {"material_id": "M01", "suggested_slot": "19:00", "commit": True},
    )
    assert locked["ok"] is False
    assert locked["error"] == "hard_requirement_locked"
    assert DraftStore(workspace[1]).count() == 0


def test_unconfirmed_conflict_can_be_stored_as_pending_draft(workspace) -> None:
    result = _tools(workspace, confirmed=None).call(
        "save_draft",
        {"material_id": "M01", "suggested_slot": "19:00", "commit": False},
    )
    assert result["ok"] is True
    assert result["created"] is True
    assert result["draft"]["committed_slot"] is None
    assert result["draft"]["hard_requirement_changed"] is False
    assert result["draft"]["publish_state"] == "not_published"
    again = _tools(workspace, confirmed=None).call(
        "save_draft",
        {"material_id": "M01", "suggested_slot": "19:00", "commit": False},
    )
    assert again["duplicate"] is True
    assert again["draft_id"] == result["draft_id"]
    assert DraftStore(workspace[1]).count() == 1


def test_rule_risk_cannot_be_saved_directly(workspace) -> None:
    result = _tools(workspace).call(
        "save_draft",
        {"material_id": "M03", "suggested_slot": "09:00", "commit": True},
    )
    assert result["error"] == "blocked_by_rule"
    assert DraftStore(workspace[1]).count() == 0


def test_parse_decision_accepts_fenced_json() -> None:
    decision = parse_decision(
        '```json\n{"action":"query_slots","arguments":{"date":"2026-11-12","slot":"18:00"},"rationale":"查询时段"}\n```'
    )
    assert decision.tool == "query_slots"
    assert decision.arguments["slot"] == "18:00"


def test_parse_decision_rejects_publish_action() -> None:
    with pytest.raises(ModelOutputError):
        parse_decision('{"action":"publish","arguments":{},"rationale":"发布"}')


def test_examples_cover_acceptance_files() -> None:
    required = [
        "01-normal",
        "02-missing-info",
        "03-rule-risk",
        "04-slot-conflict",
        "05-duplicate-submit",
        "06-save-failure",
        "07-tool-failure",
        "08-step-limit",
        "09-tool-call-limit",
        "10-confirmed-alternative",
        "11-transient-then-schedule",
    ]
    from pathlib import Path

    root = Path("examples")
    for name in required:
        assert (root / name / "input.json").exists()
        assert (root / name / "output.json").exists()
        assert (root / name / "trace.json").exists()
        output = json.loads((root / name / "output.json").read_text(encoding="utf-8"))
        blob = json.dumps(output, ensure_ascii=False)
        assert "已发布" not in blob
