import json
import os
from pathlib import Path

from knowledge_agent.policy import next_action
from knowledge_agent.schema import Action

SYSTEM_PROMPT = """你是企业知识问答助手。你只能使用工具返回的原文，不能补写资料里没有的事实。
每一轮只返回一个 JSON 对象，不要写其他文字。动作格式：
{"action":"search","query":"检索语句","reason":"..."}
{"action":"read","doc_id":"文档 ID","reason":"..."}
{"action":"ask","question":"需要用户补充的具体条件","reason":"..."}
{"action":"finish","reason":"...","result":{"answer":"...","citations":[{"doc_id":"...","version_date":null,"excerpt":"工具原文中的连续片段"}],"gaps":[],"status":"answered"}}
status 只能是 answered、conflict、insufficient_evidence、needs_clarification、tool_failure。
两份及以上文档对同一要点冲突，且没有适用范围或效力优先级时，status 必须是 conflict，并列引用，并请用户确认适用文档。版本日期只说明哪一版更晚，不能单独选边。
只检索到一份相关文档、且原文覆盖所问事实时，按该文档作答。原文没有所问事实，或文档适用范围不包含问题对象时，status 用 insufficient_evidence，并明确说明现有资料不能回答。两份原文给出同一规定时不要判成 conflict。excerpt 必须是本轮工具结果中的连续原文。"""


class ScriptedModel:
    def next_action(self, state: dict) -> Action:
        return next_action(state)


class OpenAICompatibleModel:
    def __init__(self, base_url: str, api_key: str, model: str):
        from openai import OpenAI

        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def next_action(self, state: dict) -> Action:
        payload = {
            "question": state["question"],
            "history": state["history"],
            "observations": state["observations"],
            "guard_feedback": state["guard_feedback"],
        }
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        content = response.choices[0].message.content or "{}"
        return Action.model_validate(json.loads(content))


def load_dotenv(path: str | Path = ".env") -> None:
    file_path = Path(path)
    if not file_path.exists():
        return
    for line in file_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def model_from_env(choice: str):
    if choice == "scripted":
        return ScriptedModel()
    load_dotenv()
    base_url = os.environ.get("MODEL_BASE_URL", "")
    api_key = os.environ.get("MODEL_API_KEY", "")
    model = os.environ.get("MODEL_NAME", "")
    if not base_url or not api_key or not model:
        raise SystemExit("调用真实模型需要 MODEL_BASE_URL、MODEL_API_KEY 和 MODEL_NAME。剧本模型不需要这些变量。")
    return OpenAICompatibleModel(base_url, api_key, model)
