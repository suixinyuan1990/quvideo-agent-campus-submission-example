"""四个业务工具。

工具返回事实。它们不决定下一步，也不把失败改写成成功。
用户是否同意改期，以本次请求里的 confirmed_slot 为准，不采用模型参数里的同名字段。
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from scheduling_agent.catalog import DataCatalog
from scheduling_agent.store import DraftStore

REQUIRED_FIELDS = ("title", "body", "channel", "audience", "requested_slot", "date", "content_revision")

FIELD_LABELS = {
    "title": "标题",
    "body": "正文",
    "channel": "渠道",
    "audience": "受众",
    "requested_slot": "发布时间",
    "date": "发布日期",
    "content_revision": "内容版本",
}


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def missing_fields(material: dict[str, Any]) -> list[str]:
    return [name for name in REQUIRED_FIELDS if is_blank(material.get(name))]


def field_labels(names: list[str]) -> str:
    return "、".join(FIELD_LABELS.get(name, name) for name in names)


def evaluate_rules(material: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    text = f"{material.get('title') or ''}\n{material.get('body') or ''}"
    risks: list[dict[str, str]] = []
    for item in rules.get("blocked_phrases", []):
        phrase = item.get("phrase") or ""
        if phrase and phrase in text:
            risks.append(
                {
                    "code": item.get("code") or "blocked_phrase",
                    "severity": "block",
                    "reason": item.get("reason") or "命中禁用表述",
                    "evidence": phrase,
                }
            )
    return {"risks": risks, "blocking": bool(risks)}


def format_risks(risks: list[dict[str, Any]] | None) -> list[str]:
    lines: list[str] = []
    for item in risks or []:
        reason = item.get("reason") or "规则风险"
        evidence = item.get("evidence")
        if evidence:
            lines.append(f"{reason}（{evidence}）")
        else:
            lines.append(str(reason))
    return lines


def _minutes(slot: str) -> int:
    hour, minute = slot.split(":")
    return int(hour) * 60 + int(minute)


def pick_alternative(day: dict[str, Any], preferred: str) -> str | None:
    free = [name for name, info in day.items() if not info.get("occupied")]
    try:
        current = _minutes(preferred)
        later = sorted((name for name in free if _minutes(name) > current), key=_minutes)
    except (ValueError, AttributeError):
        later = []
    if later:
        return later[0]
    ordered = sorted(free, key=_minutes)
    return ordered[0] if ordered else None


def _failure(error: str, summary: str, *, retryable: bool = False, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": error,
        "retryable": retryable,
        "summary": summary,
        "created": False,
        "duplicate": False,
    }
    payload.update(extra)
    return payload


class Toolset:
    def __init__(self, catalog: DataCatalog, store: DraftStore, user_confirmed_slot: str | None):
        self.catalog = catalog
        self.store = store
        self.user_confirmed_slot = _clean_slot(user_confirmed_slot)
        self._fault_hits: dict[str, int] = {}

    def call(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        arguments = dict(arguments or {})
        handler = {
            "read_material": self.read_material,
            "check_rules": self.check_rules,
            "query_slots": self.query_slots,
            "save_draft": self.save_draft,
        }.get(name)
        if handler is None:
            return _failure("unknown_tool", f"未知工具 {name}")
        if arguments.get("publish") is True:
            return _failure("publish_forbidden", "工具拒绝发布。当前只允许保存草稿。")
        return handler(arguments)

    def read_material(self, arguments: dict[str, Any]) -> dict[str, Any]:
        material_id = arguments.get("material_id")
        fault = self._take_fault("read_material", material_id)
        if fault is not None:
            return _failure(
                fault["error"],
                fault.get("message") or "素材读取失败",
                retryable=bool(fault.get("retryable")),
            )
        if not material_id or material_id not in self.catalog.materials:
            return _failure("not_found", f"未找到素材 {material_id or ''}".strip(), material_id=material_id)
        record = self._record(material_id, refresh=bool(arguments.get("refresh")))
        missing = missing_fields(record)
        if missing:
            summary = f"素材缺少字段：{field_labels(missing)}"
            if arguments.get("refresh"):
                summary = f"补查后仍缺少字段：{field_labels(missing)}"
        else:
            summary = (
                f"素材齐全，发布时间 {record.get('requested_slot')}（{record.get('date')}），"
                f"硬性要求={'是' if record.get('hard_requirement') else '否'}"
            )
        return {
            "ok": True,
            "summary": summary,
            "material": record,
            "missing_fields": missing,
            "complete": not missing,
            "refreshed": bool(arguments.get("refresh")),
        }

    def check_rules(self, arguments: dict[str, Any]) -> dict[str, Any]:
        material_id = arguments.get("material_id")
        fault = self._take_fault("check_rules", material_id)
        if fault is not None:
            return _failure(
                fault["error"],
                fault.get("message") or "规则检查失败",
                retryable=bool(fault.get("retryable")),
                risks=None,
                blocking=None,
            )
        if not material_id or material_id not in self.catalog.materials:
            return _failure("not_found", f"未找到素材 {material_id or ''}".strip(), risks=[], blocking=False)
        verdict = evaluate_rules(self._record(material_id, refresh=True), self.catalog.rules)
        if verdict["blocking"]:
            summary = "规则阻断：" + "、".join(format_risks(verdict["risks"]))
        else:
            summary = "规则检查通过，无风险"
        return {
            "ok": True,
            "summary": summary,
            "material_id": material_id,
            "risks": verdict["risks"],
            "blocking": verdict["blocking"],
        }

    def query_slots(self, arguments: dict[str, Any]) -> dict[str, Any]:
        date = arguments.get("date")
        slot = arguments.get("slot")
        fault = self._take_fault("query_slots", arguments.get("material_id"))
        if fault is not None:
            return _failure(
                fault["error"],
                fault.get("message") or "时段查询失败",
                retryable=bool(fault.get("retryable")),
            )
        if not date or date not in self.catalog.slots:
            return _failure("unknown_date", f"没有 {date or '该日期'} 的时段表")
        if not slot:
            return _failure("invalid_arguments", "时段查询缺少 slot")
        day = self.catalog.slots[date]
        free_slots = [name for name, info in day.items() if not info.get("occupied")]
        occupied_slots = [name for name, info in day.items() if info.get("occupied")]
        if slot not in day:
            alternative = pick_alternative(day, slot)
            return {
                "ok": True,
                "summary": f"时段表中没有 {slot}" + (f"，可用替代时段 {alternative}" if alternative else ""),
                "date": date,
                "slot": slot,
                "known": False,
                "preferred_free": False,
                "occupied_by": None,
                "alternative": alternative,
                "free_slots": free_slots,
                "occupied_slots": occupied_slots,
            }
        info = day[slot]
        alternative = None if not info.get("occupied") else pick_alternative(day, slot)
        if info.get("occupied"):
            occupied_by = info.get("occupied_by") or "已有排期"
            summary = f"{slot} 已被占用（{occupied_by}）"
            summary += f"，可用替代时段 {alternative}" if alternative else "，没有可用替代时段"
            preferred_free = False
        else:
            occupied_by = None
            summary = f"{slot} 可用"
            preferred_free = True
        return {
            "ok": True,
            "summary": summary,
            "date": date,
            "slot": slot,
            "known": True,
            "preferred_free": preferred_free,
            "occupied_by": occupied_by,
            "alternative": alternative,
            "free_slots": free_slots,
            "occupied_slots": occupied_slots,
        }

    def save_draft(self, arguments: dict[str, Any]) -> dict[str, Any]:
        material_id = arguments.get("material_id")
        suggested = _clean_slot(arguments.get("suggested_slot"))
        if not material_id or suggested is None or "commit" not in arguments:
            return _failure("invalid_arguments", "保存草稿缺少素材、建议时段或 commit 标记")
        if material_id not in self.catalog.materials:
            return _failure("not_found", f"未找到素材 {material_id}")
        material = self._record(material_id, refresh=True)
        missing = missing_fields(material)
        if missing:
            return _failure("incomplete_material", f"素材缺少{field_labels(missing)}，拒绝保存草稿")
        if material.get("queue_status") != "pending":
            return _failure("not_pending", "素材不在待处理队列，拒绝保存草稿")
        verdict = evaluate_rules(material, self.catalog.rules)
        if verdict["blocking"]:
            return _failure("blocked_by_rule", "素材有阻断级规则风险，拒绝保存排期草稿", risks=verdict["risks"])
        commit = bool(arguments.get("commit"))
        requested = material.get("requested_slot")
        confirmed = self.user_confirmed_slot
        claimed = _clean_slot(arguments.get("confirmed_slot"))
        if claimed not in (None, confirmed):
            return _failure("confirmation_mismatch", "模型声明的确认时段与用户请求不一致，拒绝保存")
        if commit and suggested != requested and confirmed != suggested:
            error = "hard_requirement_locked" if material.get("hard_requirement") else "confirmation_required"
            return _failure(error, "未经用户确认，不能改写发布时间")
        day = self.catalog.slots.get(material.get("date") or "", {})
        slot_info = day.get(suggested)
        if slot_info is None:
            return _failure("unknown_slot", f"时段表中没有 {suggested}")
        if slot_info.get("occupied"):
            return _failure("slot_occupied", f"{suggested} 已被占用，拒绝写入草稿")
        fault = self._take_fault("save_draft", material_id)
        if fault is not None:
            return _failure(
                fault["error"],
                fault.get("message") or "草稿保存失败",
                retryable=bool(fault.get("retryable")),
            )
        changed = bool(commit and suggested != requested)
        if not commit:
            confirmation_status = "pending"
            committed = None
            review_status = "pending_confirmation"
        elif changed:
            confirmation_status = "confirmed"
            committed = suggested
            review_status = "confirmed_draft"
        else:
            confirmation_status = "not_required"
            committed = suggested
            review_status = "ready_draft"
        identity = {
            "material_id": material_id,
            "content_revision": material.get("content_revision"),
            "title": material.get("title"),
            "body": material.get("body"),
            "channel": material.get("channel"),
            "audience": material.get("audience"),
            "date": material.get("date"),
            "requested_slot": requested,
            "suggested_slot": suggested,
            "commit": commit,
            "confirmed_slot": confirmed or "",
        }
        draft_id = "D-" + hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        existing = self.store.find(draft_id)
        if existing is not None:
            return {
                "ok": True,
                "created": False,
                "duplicate": True,
                "summary": f"相同请求已有草稿 {draft_id}，未新建",
                "draft_id": draft_id,
                "draft": existing,
                "publish_state": "not_published",
                "confirmation_status": existing.get("confirmation_status"),
                "store_draft_count": self.store.count(),
            }
        superseded_ids = self._supersede_pending(
            material_id=material_id,
            content_revision=material.get("content_revision"),
            date=material.get("date"),
            requested_slot=requested,
            successor_id=draft_id,
        )
        draft = {
            "draft_id": draft_id,
            "material_id": material_id,
            "content_revision": material.get("content_revision"),
            "date": material.get("date"),
            "requested_slot": requested,
            "suggested_slot": suggested,
            "committed_slot": committed,
            "hard_requirement": bool(material.get("hard_requirement")),
            "hard_requirement_changed": changed,
            "change_authorized": changed,
            "confirmation_status": confirmation_status,
            "review_status": review_status,
            "risk_reasons": format_risks(verdict["risks"]),
            "publish_state": "not_published",
        }
        self.store.add(draft)
        payload = {
            "ok": True,
            "created": True,
            "duplicate": False,
            "summary": f"已新建草稿 {draft_id}，未发布",
            "draft_id": draft_id,
            "draft": draft,
            "publish_state": "not_published",
            "confirmation_status": confirmation_status,
            "store_draft_count": self.store.count(),
        }
        if superseded_ids:
            payload["superseded_draft_ids"] = superseded_ids
        return payload

    def _supersede_pending(
        self,
        *,
        material_id: str,
        content_revision: Any,
        date: Any,
        requested_slot: Any,
        successor_id: str,
    ) -> list[str]:
        """新草稿落盘前，把同一版本上仍待确认的旧建议标成已接替。

        只改确认状态，不改写硬性发布时间，也不把草稿标成已发布。
        保存失败和重复保存不会走到这里。
        """
        superseded: list[str] = []
        for item in self.store.drafts:
            if item.get("draft_id") == successor_id:
                continue
            if item.get("material_id") != material_id:
                continue
            if item.get("content_revision") != content_revision:
                continue
            if item.get("date") != date or item.get("requested_slot") != requested_slot:
                continue
            if item.get("confirmation_status") != "pending":
                continue
            item["confirmation_status"] = "superseded"
            item["review_status"] = "superseded"
            item["superseded_by"] = successor_id
            superseded.append(item["draft_id"])
        if superseded:
            self.store.save()
        return superseded

    def _record(self, material_id: str, *, refresh: bool) -> dict[str, Any]:
        record = copy.deepcopy(self.catalog.materials[material_id])
        if refresh:
            record.update(copy.deepcopy(self.catalog.supplements.get(material_id) or {}))
        return record

    def _take_fault(self, tool_name: str, material_id: Any) -> dict[str, Any] | None:
        specs = self.catalog.faults.get(tool_name, [])
        if isinstance(specs, dict):
            specs = [specs]
        for spec in specs:
            if spec.get("material_id") != material_id:
                continue
            key = f"{tool_name}:{material_id}:{spec.get('error')}"
            used = self._fault_hits.get(key, 0)
            if used >= int(spec.get("fail_count", 1)):
                return None
            self._fault_hits[key] = used + 1
            return spec
        return None


def _clean_slot(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
