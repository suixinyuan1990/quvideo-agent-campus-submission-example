"""Scripted model for acceptance, and an OpenAI-compatible client."""

import json
import os
from typing import Any

from openai import OpenAI
from pydantic import TypeAdapter

from script_agent.policy import decide
from script_agent.schema import Action

_ACTION = TypeAdapter(Action)

SYSTEM = """你是短视频脚本助手。每一轮只返回一个 JSON 对象，不要写解释。
可用动作：
{"action":"search","query":"检索语句"}
{"action":"draft","title":"标题","shots":[{"index":1,"visual":"画面","narration":"旁白","subtitle":"字幕","source_ids":["来源ID"]}]}
{"action":"estimate"}
{"action":"check_rules"}
{"action":"ask","missing":["主题"],"message":"需要补充什么"}
{"action":"finish","status":"completed","message":""}
finish 的 status 还可以是 no_material、unsatisfied、needs_input。
产品事实只能来自本轮检索结果的 body。不要写入 body 里没有的百分数或“倍”。
时长使用工具返回值，不要自己填写 duration。
检索为空时，改写查询再检索，或 ask 请求补充。改写后仍为空就 finish 为 no_material。
估算超过目标或阻断规则未通过时，draft 压缩或改写后再检查；确实不能同时满足就 finish 为 unsatisfied。
只有估算未超过目标且规则检查通过时，才能 finish 为 completed。
"""


class ScriptModel:
    def act(self, state: Any) -> Action:
        return decide(state)


class OpenAIModel:
    def __init__(self, base_url: str, api_key: str, model_name: str) -> None:
        self.model_name = model_name
        self.client = OpenAI(base_url=base_url, api_key=api_key)

    def act(self, state: Any) -> Action:
        payload = {
            "theme": state.request.theme,
            "duration_sec": state.request.duration_sec,
            "style": state.request.effective_style,
            "audience": state.request.audience,
            "platform": state.request.platform,
            "rules": [rule.model_dump(mode="json") for rule in state.rules],
            "hits": [hit.model_dump(mode="json") for hit in state.hits],
            "draft": state.draft.model_dump(mode="json") if state.draft else None,
            "estimate": state.estimate.model_dump(mode="json") if state.estimate else None,
            "check": state.check.model_dump(mode="json") if state.check else None,
            "guard_error": state.guard_error,
            "note": state.note,
            "search_count": state.search_count,
            "revisions": state.revisions,
        }
        response = self.client.chat.completions.create(
            model=self.model_name,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        content = response.choices[0].message.content or ""
        return parse_action(content)


def parse_action(content: str) -> Action:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    return _ACTION.validate_python(json.loads(text))


def load_dotenv(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
