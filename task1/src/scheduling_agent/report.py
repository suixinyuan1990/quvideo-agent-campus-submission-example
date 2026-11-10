"""把工具观察汇总成交付结果。

保存是否成功、是否发布，只看工具返回。模型的结束语不能把失败改成成功，也不能写成已发布。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scheduling_agent.tools import field_labels, format_risks
from scheduling_agent.types import Observation


@dataclass
class RunMeta:
    run_status: str
    incomplete_reason: str | None
    decision_count: int
    tool_calls_used: int
    max_steps: int
    max_tool_calls: int
    store_draft_count: int


def build_report(request: dict[str, Any], observations: list[Observation], meta: RunMeta) -> dict[str, Any]:
    reads = [item for item in observations if item.tool == "read_material"]
    rules = [item for item in observations if item.tool == "check_rules"]
    slots = [item for item in observations if item.tool == "query_slots"]
    saves = [item for item in observations if item.tool == "save_draft"]
    last_read = reads[-1] if reads else None
    material = (last_read.payload.get("material") if last_read and last_read.ok else None) or {}

    report: dict[str, Any] = {
        "run_status": meta.run_status,
        "outcome": None,
        "material_id": request.get("material_id"),
        "review_status": None,
        "risk_reasons": [],
        "requested_slot": material.get("requested_slot"),
        "requested_date": material.get("date"),
        "hard_requirement": material.get("hard_requirement") if material else None,
        "suggested_slot": None,
        "committed_slot": None,
        "hard_requirement_changed": False,
        "change_authorized": False,
        "confirmation_status": None,
        "pending_confirmations": [],
        "draft_save_status": "not_saved",
        "draft_id": None,
        "saved_draft": None,
        "publish_state": "not_published",
        "save_error": None,
        "tool_error": None,
        "message": "",
        "incomplete_reason": meta.incomplete_reason,
        "store_draft_count": meta.store_draft_count,
        "progress": {
            "material_loaded": bool(last_read and last_read.ok),
            "material_complete": bool(last_read and last_read.ok and not last_read.payload.get("missing_fields")),
            "rules_checked": bool(rules and rules[-1].ok),
            "rules_clear": bool(rules and rules[-1].ok and not rules[-1].payload.get("blocking")),
            "slots_checked": bool(slots and slots[-1].ok),
            "save_called": bool(saves),
        },
        "limits": {
            "max_steps": meta.max_steps,
            "max_tool_calls": meta.max_tool_calls,
            "decision_count": meta.decision_count,
            "tool_calls_used": meta.tool_calls_used,
            "hit_limit": meta.run_status == "incomplete",
        },
    }
    if rules and rules[-1].ok:
        report["risk_reasons"] = format_risks(rules[-1].payload.get("risks"))

    if meta.run_status == "incomplete":
        report["outcome"] = "incomplete"
        report["review_status"] = "incomplete"
        report["message"] = meta.incomplete_reason or "任务未完成"
        report["incomplete_reason"] = report["message"]
        _apply_save(report, saves)
        if report["draft_save_status"] == "not_saved":
            report["suggested_slot"] = None
            report["committed_slot"] = None
        return _guard(report, observations)

    if not request.get("material_id"):
        return _finish_case(
            report,
            observations,
            outcome="insufficient_information",
            review_status="insufficient_information",
            message="请求没有素材 ID，无法读取素材，未发布。",
        )

    if last_read is None or not last_read.ok:
        error = last_read.payload.get("error") if last_read else "not_read"
        if error == "not_found":
            return _finish_case(
                report,
                observations,
                outcome="insufficient_information",
                review_status="insufficient_information",
                message="未找到该素材，无法排期，未发布。",
                tool_error=error,
            )
        return _finish_case(
            report,
            observations,
            outcome="tool_failure",
            review_status="blocked_tool_failure",
            message="素材读取失败，无法排期，未发布。",
            tool_error=error,
        )

    missing = last_read.payload.get("missing_fields") or []
    if missing:
        looked_again = len(reads) >= 2
        if looked_again:
            pending = f"缺少字段：{field_labels(missing)}。已补查，仍然没有这些内容。"
            message = "素材信息不足，补查后仍缺少必要字段，已停止排期，未保存草稿，未发布。"
        else:
            pending = f"缺少字段：{field_labels(missing)}。"
            message = "素材信息不足，已停止排期，未保存草稿，未发布。"
        report["pending_confirmations"] = [pending]
        return _finish_case(
            report,
            observations,
            outcome="insufficient_information",
            review_status="insufficient_information",
            message=message,
        )

    if material.get("queue_status") != "pending":
        return _finish_case(
            report,
            observations,
            outcome="not_pending",
            review_status="not_pending",
            message="素材不在待处理队列，未排期，未发布。",
        )

    if not rules or not rules[-1].ok:
        error = rules[-1].payload.get("error") if rules else "not_checked"
        report["pending_confirmations"] = ["没有可靠的规则结果，已停止排期。"]
        return _finish_case(
            report,
            observations,
            outcome="tool_failure",
            review_status="blocked_tool_failure",
            message="规则检查失败，没有可靠的风险结论，已停止排期，未保存草稿，未发布。",
            tool_error=error,
        )

    if rules[-1].payload.get("blocking"):
        report["pending_confirmations"] = ["存在阻断级规则风险，未排期。"]
        return _finish_case(
            report,
            observations,
            outcome="blocked_by_rule",
            review_status="blocked",
            message="素材有阻断级规则风险，已停止排期，未保存草稿，未发布。",
        )

    if not slots or not slots[-1].ok:
        error = slots[-1].payload.get("error") if slots else "not_checked"
        return _finish_case(
            report,
            observations,
            outcome="tool_failure" if slots else "not_scheduled",
            review_status="blocked_tool_failure" if slots else "not_scheduled",
            message="时段查询失败，不能确认排期，未保存草稿，未发布。" if slots else "尚未查询时段，未保存草稿，未发布。",
            tool_error=error if slots else None,
        )

    slot_payload = slots[-1].payload
    suggested = material.get("requested_slot") if slot_payload.get("preferred_free") else slot_payload.get("alternative")
    report["suggested_slot"] = suggested
    if not slot_payload.get("preferred_free"):
        report["pending_confirmations"] = _conflict_pending(material, slot_payload)
        report["confirmation_status"] = "pending"

    if not saves:
        if slot_payload.get("preferred_free"):
            return _finish_case(
                report,
                observations,
                outcome="not_scheduled",
                review_status="not_scheduled",
                message="时段可用，但没有保存草稿，未发布。",
            )
        return _finish_case(
            report,
            observations,
            outcome="pending_confirmation",
            review_status="pending_confirmation",
            message="要求的时段不可用，未保存草稿，未发布。请确认可接受的其他时间。",
        )

    _apply_save(report, saves)
    last_save = saves[-1]
    if not last_save.ok:
        report["suggested_slot"] = suggested
        report["committed_slot"] = None
        report["message"] = f"草稿保存失败（{last_save.payload.get('error')}），未写入草稿，未发布。"
        report["outcome"] = "save_failed"
        report["review_status"] = "save_failed"
        return _guard(report, observations)

    draft = last_save.payload.get("draft") or {}
    report["suggested_slot"] = draft.get("suggested_slot")
    report["committed_slot"] = draft.get("committed_slot")
    report["hard_requirement_changed"] = bool(draft.get("hard_requirement_changed"))
    report["change_authorized"] = bool(draft.get("change_authorized"))
    report["confirmation_status"] = draft.get("confirmation_status")
    report["review_status"] = draft.get("review_status")
    if draft.get("confirmation_status") != "pending":
        report["pending_confirmations"] = []
    superseded_ids = last_save.payload.get("superseded_draft_ids") or []
    if superseded_ids:
        report["superseded_draft_ids"] = list(superseded_ids)
    if last_save.payload.get("duplicate") and draft.get("confirmation_status") == "superseded":
        report["message"] = "该待确认草稿已被后续排期接替，未新建另一份，未发布。"
        report["outcome"] = "superseded"
    elif last_save.payload.get("duplicate"):
        report["message"] = "相同请求已存在草稿，未新建另一份，未发布。"
        report["outcome"] = _outcome_for_review(draft.get("review_status"))
    elif draft.get("confirmation_status") == "pending":
        report["message"] = f"已保存排期草稿：建议时段 {draft.get('suggested_slot')}，待确认，未发布。"
        report["outcome"] = "pending_confirmation"
    elif draft.get("review_status") == "confirmed_draft":
        report["message"] = "已按用户确认的时段保存排期草稿，未发布。"
        report["outcome"] = "confirmed_draft"
    else:
        report["message"] = "已按要求时段保存排期草稿，未发布。"
        report["outcome"] = "scheduled_draft"
    return _guard(report, observations)


def _conflict_pending(material: dict[str, Any], slot: dict[str, Any]) -> list[str]:
    requested = material.get("requested_slot")
    occupied_by = slot.get("occupied_by") or "已有排期"
    alternative = slot.get("alternative")
    label = "硬性发布时间" if material.get("hard_requirement") else "要求的发布时间"
    if alternative:
        return [f"{label} {requested} 已被占用（{occupied_by}），建议 {alternative}。未经确认不会改写该要求。"]
    return [f"{label} {requested} 已被占用（{occupied_by}），没有可用替代时段。请确认其他可接受时间。"]


def _apply_save(report: dict[str, Any], saves: list[Observation]) -> None:
    if not saves:
        return
    last = saves[-1]
    if not last.ok:
        report["draft_save_status"] = "failed"
        report["save_error"] = last.payload.get("error")
        report["draft_id"] = None
        report["saved_draft"] = None
        return
    report["draft_save_status"] = "duplicate" if last.payload.get("duplicate") else "saved"
    report["draft_id"] = last.payload.get("draft_id")
    report["saved_draft"] = last.payload.get("draft")


def _finish_case(
    report: dict[str, Any],
    observations: list[Observation],
    *,
    outcome: str,
    review_status: str,
    message: str,
    tool_error: str | None = None,
) -> dict[str, Any]:
    report["outcome"] = outcome
    report["review_status"] = review_status
    report["message"] = message
    report["tool_error"] = tool_error
    report["draft_save_status"] = "not_saved"
    return _guard(report, observations)


def _outcome_for_review(review_status: str | None) -> str:
    return {
        "pending_confirmation": "pending_confirmation",
        "confirmed_draft": "confirmed_draft",
        "ready_draft": "scheduled_draft",
    }.get(review_status or "", "scheduled_draft")


def _guard(report: dict[str, Any], observations: list[Observation]) -> dict[str, Any]:
    if report["publish_state"] != "not_published":
        raise RuntimeError("结果把任务标成了发布。")
    if "已发布" in json_text(report):
        raise RuntimeError("结果文案出现了已发布。")
    created = [
        item
        for item in observations
        if item.tool == "save_draft" and item.ok and item.payload.get("created") and not item.payload.get("duplicate")
    ]
    duplicated = [
        item for item in observations if item.tool == "save_draft" and item.ok and item.payload.get("duplicate")
    ]
    failed = [item for item in observations if item.tool == "save_draft" and not item.ok]
    status = report["draft_save_status"]
    if status == "saved" and not created:
        raise RuntimeError("没有成功新建观察，却报告了保存成功。")
    if status == "duplicate" and not duplicated:
        raise RuntimeError("没有重复观察，却报告了重复草稿。")
    if status == "failed" and not failed:
        raise RuntimeError("没有失败观察，却报告了保存失败。")
    draft = report.get("saved_draft")
    if draft is not None and draft.get("publish_state") != "not_published":
        raise RuntimeError("草稿记录被标成了发布。")
    return report


def json_text(data: Any) -> str:
    import json

    return json.dumps(data, ensure_ascii=False)
