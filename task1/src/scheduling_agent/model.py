"""决策模型。

`ObservationDecisionModel.decide` 是默认的模型步骤。执行循环每观察一次就重新调用它。
函数内部没有按素材编号写死的剧本；下一步只由当前请求和已经返回的工具结果决定。

远程模型使用同一个 `Decision` 结构。验收轨迹不依赖网络。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from scheduling_agent.types import TOOL_NAMES, Decision, ModelConfigError, ModelOutputError, Observation


class ObservationDecisionModel:
    """根据工具观察选择下一动作。每次调用只处理眼前的历史。"""

    def decide(self, request: dict[str, Any], observations: list[Observation]) -> Decision:
        material_id = request.get("material_id")
        if not material_id:
            return self._finish("请求没有素材 ID，无法继续。")

        reads = [item for item in observations if item.tool == "read_material"]
        rules = [item for item in observations if item.tool == "check_rules"]
        slots = [item for item in observations if item.tool == "query_slots"]
        saves = [item for item in observations if item.tool == "save_draft"]

        if not reads:
            return self._tool(
                "read_material",
                {"material_id": material_id, "refresh": False},
                "还没有素材观察结果，先读取素材元数据和发布时间要求。",
            )

        last_read = reads[-1]
        if not last_read.ok:
            if last_read.payload.get("retryable") and len(reads) < 2:
                return self._tool(
                    "read_material",
                    {"material_id": material_id, "refresh": True},
                    "素材读取失败且错误可补查，决定再读一次。",
                )
            return self._finish("素材读取失败，阻断排期。")

        material = last_read.payload.get("material") or {}
        if material.get("queue_status") != "pending":
            return self._finish("素材不在待处理队列，不排期。")

        missing = last_read.payload.get("missing_fields") or []
        if missing:
            if len(reads) < 2:
                return self._tool(
                    "read_material",
                    {"material_id": material_id, "refresh": True},
                    "素材缺少必要字段，先补查一次，不进入规则检查和排期。",
                )
            return self._finish("补查后素材仍然缺少必要字段，阻断排期。")

        if not rules:
            return self._tool(
                "check_rules",
                {"material_id": material_id},
                "素材字段已经齐全，下一步检查审核规则。",
            )

        last_rule = rules[-1]
        if not last_rule.ok:
            if last_rule.payload.get("retryable") and len(rules) < 2:
                return self._tool(
                    "check_rules",
                    {"material_id": material_id},
                    "规则工具临时失败，决定补查一次；没有可靠规则结果之前不排期。",
                )
            return self._finish("规则检查仍然没有可靠结果，阻断排期。")
        if last_rule.payload.get("blocking"):
            return self._finish("观察结果含阻断级规则风险，阻断排期。")

        if not slots:
            return self._tool(
                "query_slots",
                {"date": material.get("date"), "slot": material.get("requested_slot"), "material_id": material_id},
                "规则检查通过，查询要求的发布时间是否可用。",
            )

        last_slot = slots[-1]
        if not last_slot.ok:
            if last_slot.payload.get("retryable") and len(slots) < 2:
                return self._tool(
                    "query_slots",
                    {"date": material.get("date"), "slot": material.get("requested_slot"), "material_id": material_id},
                    "时段查询失败，决定补查一次。",
                )
            return self._finish("时段查询没有可靠结果，阻断排期。")

        if saves:
            return self._finish(self._save_finish_rationale(saves[-1]))

        return self._choose_save(request, material, last_slot)

    def _choose_save(self, request: dict[str, Any], material: dict[str, Any], slot: Observation) -> Decision:
        requested = material.get("requested_slot")
        confirmed = _clean(request.get("confirmed_slot"))
        free_slots = set(slot.payload.get("free_slots") or [])
        if slot.payload.get("preferred_free"):
            return self._tool(
                "save_draft",
                {
                    "material_id": request.get("material_id"),
                    "suggested_slot": requested,
                    "commit": True,
                    "confirmed_slot": confirmed,
                },
                "要求的时段可用，按该时段保存草稿。",
            )
        if confirmed:
            if confirmed not in free_slots:
                return self._finish("用户确认的时段不可用，不改写到其他时段。")
            return self._tool(
                "save_draft",
                {
                    "material_id": request.get("material_id"),
                    "suggested_slot": confirmed,
                    "commit": True,
                    "confirmed_slot": confirmed,
                },
                "用户已经确认替代时段，且该时段可用。按确认结果保存草稿。",
            )
        alternative = slot.payload.get("alternative")
        if not alternative:
            return self._finish("要求的时段已被占用，没有可用替代时段。停止保存，等待用户确认其他时间。")
        if material.get("hard_requirement"):
            rationale = "要求的时段已被占用，而且用户没有确认替代时段。建议可用替代时段并标记待确认，不改写硬性发布时间。"
        else:
            rationale = "要求的时段已被占用，而且用户没有确认替代时段。建议可用替代时段并标记待确认，不直接改写用户要求的时间。"
        return self._tool(
            "save_draft",
            {
                "material_id": request.get("material_id"),
                "suggested_slot": alternative,
                "commit": False,
                "confirmed_slot": None,
            },
            rationale,
        )

    @staticmethod
    def _save_finish_rationale(save: Observation) -> str:
        if not save.ok:
            return "保存工具返回失败。结束并报告失败。"
        if save.payload.get("duplicate"):
            return "保存结果标明这份草稿已经存在。结束，不新建另一份。"
        if save.payload.get("confirmation_status") == "pending":
            return "草稿已保存，确认状态为待确认，硬性发布时间没有改写。结束。"
        return "草稿已保存。结束。"

    @staticmethod
    def _tool(name: str, arguments: dict[str, Any], rationale: str) -> Decision:
        return Decision(kind="tool", tool=name, arguments=arguments, rationale=rationale)

    @staticmethod
    def _finish(rationale: str) -> Decision:
        return Decision(kind="finish", rationale=rationale)


SYSTEM_PROMPT = """你是素材审核与发布排期代理。每次只输出一个 JSON 对象，不要写别的文字。
可选 action：read_material、check_rules、query_slots、save_draft、finish。
工具参数：
- read_material: {"material_id": string, "refresh": boolean}
- check_rules: {"material_id": string}
- query_slots: {"date": string, "slot": string, "material_id": string}
- save_draft: {"material_id": string, "suggested_slot": string, "commit": boolean, "confirmed_slot": string|null}
- finish: {}
约束：
- 只能保存草稿，不能发布。不要发明发布动作。
- 用户没有在请求里确认替代时段时，不要 commit 一个不同的时间。可以建议替代时段并用 commit=false 保存待确认草稿。
- 字段缺失时先 refresh 补查一次；补查后仍缺失就 finish。
- 规则结果为阻断时 finish，不要排期。
- 工具返回 retryable=true 时可以补查一次。retryable=false 时不要再调用该工具。
- 保存工具若返回失败或重复，下一步 finish，不要把失败说成成功。
JSON 形式：{"action": "...", "arguments": {}, "rationale": "一句中文决策依据"}
"""


class LLMDecisionModel:
    """OpenAI Chat Completions 兼容适配器。解析失败时抛出，由循环记为未完成。"""

    def __init__(self, complete_fn: Any | None = None):
        self._complete = complete_fn or _openai_complete
        self.base_url = os.environ.get("LLM_BASE_URL", "").strip()
        self.api_key = os.environ.get("LLM_API_KEY", "").strip()
        self.model_name = os.environ.get("LLM_MODEL", "").strip()
        if self._complete is _openai_complete and not (self.base_url and self.api_key and self.model_name):
            raise ModelConfigError("使用远程模型时需要 LLM_BASE_URL、LLM_API_KEY 和 LLM_MODEL。")

    def decide(self, request: dict[str, Any], observations: list[Observation]) -> Decision:
        prompt = _render_prompt(request, observations)
        try:
            content = self._complete(
                base_url=self.base_url,
                api_key=self.api_key,
                model_name=self.model_name,
                prompt=prompt,
            )
        except ModelOutputError:
            raise
        except Exception as exc:  # noqa: BLE001 - 网络与解析外的失败都要变成可报告状态
            raise ModelOutputError(f"模型调用失败：{exc.__class__.__name__}") from exc
        return parse_decision(content)


def parse_decision(text: str) -> Decision:
    raw = text.strip()
    if raw.startswith("```"):
        lines = [line for line in raw.splitlines() if not line.strip().startswith("```")]
        raw = "\n".join(lines).strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ModelOutputError("模型输出里没有 JSON 对象。")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ModelOutputError("模型输出不是合法 JSON。") from exc
    action = data.get("action")
    rationale = str(data.get("rationale") or "").strip() or "模型未给出依据。"
    arguments = data.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ModelOutputError("arguments 必须是对象。")
    if action == "finish":
        return Decision(kind="finish", rationale=rationale)
    if action not in TOOL_NAMES:
        raise ModelOutputError(f"模型选择了不允许的动作：{action}")
    return Decision(kind="tool", tool=action, arguments=arguments, rationale=rationale)


def make_model(name: str) -> ObservationDecisionModel | LLMDecisionModel:
    if name == "local":
        return ObservationDecisionModel()
    if name == "llm":
        return LLMDecisionModel()
    raise ValueError(f"未知模型：{name}")


def _render_prompt(request: dict[str, Any], observations: list[Observation]) -> str:
    history = [
        {
            "tool": item.tool,
            "arguments": item.arguments,
            "ok": item.ok,
            "summary": item.summary,
            "payload": item.payload,
        }
        for item in observations
    ]
    visible = {
        "material_id": request.get("material_id"),
        "confirmed_slot": request.get("confirmed_slot"),
    }
    return (
        "用户请求：\n"
        + json.dumps(visible, ensure_ascii=False)
        + "\n已有工具观察：\n"
        + json.dumps(history, ensure_ascii=False)
    )


def _openai_complete(*, base_url: str, api_key: str, model_name: str, prompt: str) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": model_name,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ModelOutputError(f"模型接口返回 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ModelOutputError("模型接口不可达") from exc
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelOutputError("模型接口没有返回消息内容。") from exc


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
