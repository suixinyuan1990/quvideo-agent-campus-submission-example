"""可选的 OpenAI 兼容模型。只提议动作，不写步骤状态。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from src.agent.files import ROOT

ENV_KEYS = ("MODEL_API_KEY", "MODEL_BASE_URL", "MODEL_NAME")


def load_env_file(path: Path | None = None) -> None:
    env_path = ROOT / ".env" if path is None else path
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def model_settings() -> dict[str, str]:
    load_env_file()
    return {key: os.environ.get(key, "").strip() for key in ENV_KEYS}


def model_configured() -> bool:
    settings = model_settings()
    return all(settings.values())


def parse_model_response(payload: dict) -> dict:
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("模型响应缺少 choices") from exc
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        arguments = tool_calls[0].get("function", {}).get("arguments", "")
        if isinstance(arguments, dict):
            action = arguments
        else:
            action = json.loads(arguments)
    else:
        content = message.get("content") or ""
        action = json.loads(content)
    if not isinstance(action, dict) or "action" not in action:
        raise ValueError("模型没有返回动作")
    return action


class ModelDecider:
    source = "model"

    def __init__(self, transport=None) -> None:
        self.transport = transport or post_chat

    def propose(self, observation: dict) -> dict:
        if not model_configured() and self.transport is post_chat:
            return {"action": "stop", "reason": "未配置模型，方案未保存。", "error": True}
        try:
            payload = self.transport(observation, model_settings())
            action = parse_model_response(payload)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, OSError) as exc:
            return {"action": "stop", "reason": f"模型调用失败：{exc}。方案未保存。", "error": True}
        action.setdefault("reason", "")
        return action


def post_chat(observation: dict, settings: dict[str, str]) -> dict:
    url = settings["MODEL_BASE_URL"].rstrip("/") + "/chat/completions"
    body = {
        "model": settings["MODEL_NAME"],
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是内容活动规划助手。只提议下一步动作，不宣布步骤成功，也不修改费用。"
                    "费用以工具返回为准。估算超过预算时不要 save，应 switch 或 stop。"
                    "动作只能是 continue、switch、retry、save、stop、reuse。"
                ),
            },
            {"role": "user", "content": json.dumps(observation, ensure_ascii=False)},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "propose_action",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["continue", "switch", "retry", "save", "stop", "reuse"]},
                            "to_plan": {"type": "string"},
                            "plan_id": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["action", "reason"],
                    },
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "propose_action"}},
    }
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {settings['MODEL_API_KEY']}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))
