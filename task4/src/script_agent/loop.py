"""Decision loop. The model picks the next action; tools own seconds and rule hits."""

from dataclasses import dataclass, field

from script_agent.corpus import Corpus
from script_agent.guard import completion_problems
from script_agent.model import ScriptModel
from script_agent.schema import (
    CheckResult,
    Draft,
    Estimate,
    FinishAction,
    Hit,
    Request,
    Result,
    Rule,
    RunOutput,
    ShotDelivery,
)
from script_agent.textutil import chars_per_second, content_theme, target_ms
from script_agent.tools import FailurePlan, ToolFailure, check_draft, estimate_draft, search_materials

MAX_ACTIONS = 12
MAX_SEARCH = 3
MAX_REVISIONS = 2
TOOL_NAME = {"search": "素材检索", "estimate": "时长估算", "check_rules": "规则检查"}
TOOL_GAP = {"search": "素材未核实", "estimate": "时长未估算", "check_rules": "规则未检查"}


@dataclass
class AgentState:
    request: Request
    rules: list[Rule]
    searches: list[list[Hit]] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    draft: Draft | None = None
    revisions: int = 0
    estimate: Estimate | None = None
    check: CheckResult | None = None
    guard_error: str | None = None
    note: str | None = None

    @property
    def search_count(self) -> int:
        return len(self.searches)

    @property
    def hits(self) -> list[Hit]:
        found: list[Hit] = []
        seen: set[str] = set()
        for batch in self.searches:
            for hit in batch:
                if hit.source_id not in seen:
                    seen.add(hit.source_id)
                    found.append(hit)
        return found


def run(
    request: Request,
    corpus: Corpus,
    rules: list[Rule] | None = None,
    model: ScriptModel | None = None,
    failures: FailurePlan | None = None,
) -> RunOutput:
    rules = list(rules or [])
    model = model or ScriptModel()
    failures = failures or FailurePlan()
    trace: list[dict] = []
    missing = _missing_fields(request)
    if missing:
        message = "缺少关键信息：" + "、".join(missing)
        trace.append({"action": "ask", "arguments": {"missing": missing}, "ok": True, "observation": {}})
        return RunOutput(input=request, result=_bare(request, "needs_input", message), trace=trace)
    if request.theme is not None and not content_theme(request.theme):
        message = "主题无法形成检索查询，请补充具体的产品或功能。"
        trace.append({"action": "ask", "arguments": {"missing": ["主题"]}, "ok": True, "observation": {}})
        return RunOutput(input=request, result=_bare(request, "needs_input", message), trace=trace)

    state = AgentState(request=request, rules=rules)
    guard_returns = 0
    for _ in range(MAX_ACTIONS):
        action = model.act(state)
        if action.action == "search":
            if state.search_count >= MAX_SEARCH:
                state.note = "检索次数已用尽"
                trace.append(
                    {
                        "action": "search",
                        "arguments": {"query": action.query},
                        "ok": False,
                        "observation": {"error": state.note},
                    }
                )
                continue
            try:
                hits = _call(
                    "search",
                    {"query": action.query},
                    lambda: search_materials(corpus, action.query, failures),
                    trace,
                )
            except ToolFailure as exc:
                return _failure_output(request, state, trace, exc.tool)
            state.searches.append(hits)
            state.queries.append(action.query)
            state.note = None
            continue
        if action.action == "draft":
            incoming = Draft(title=action.title, shots=action.shots)
            if state.draft is not None and _same_script(state.draft, incoming):
                message = "继续调整不会缩短脚本，预计总时长仍超过目标。"
                if state.estimate is not None:
                    message = (
                        f"继续调整不会缩短脚本，预计总时长仍为 {state.estimate.total_sec:.3f} 秒，"
                        f"超过目标 {request.duration_sec:g} 秒。"
                    )
                trace.append({"action": "finish", "arguments": {"status": "unsatisfied", "message": message}, "ok": True, "observation": {}})
                return RunOutput(input=request, result=_from_state(state, "unsatisfied", message), trace=trace)
            if state.draft is not None and state.revisions >= MAX_REVISIONS:
                message = "脚本调整次数已用尽，仍未同时满足时长和规则。"
                trace.append({"action": "finish", "arguments": {"status": "unsatisfied", "message": message}, "ok": True, "observation": {}})
                return RunOutput(input=request, result=_from_state(state, "unsatisfied", message), trace=trace)
            if state.draft is not None:
                state.revisions += 1
            state.draft = Draft(title=action.title, shots=action.shots)
            state.estimate = None
            state.check = None
            state.guard_error = None
            trace.append(
                {
                    "action": "draft",
                    "arguments": action.model_dump(mode="json"),
                    "ok": True,
                    "observation": {"revision": state.revisions},
                }
            )
            continue
        if action.action == "estimate":
            if state.draft is None:
                state.note = "还没有草稿"
                continue
            try:
                state.estimate = _call(
                    "estimate",
                    {},
                    lambda: estimate_draft(state.draft, request.effective_style, failures),
                    trace,
                )
            except ToolFailure as exc:
                return _failure_output(request, state, trace, exc.tool)
            continue
        if action.action == "check_rules":
            if state.draft is None:
                state.note = "还没有草稿"
                continue
            try:
                state.check = _call(
                    "check_rules",
                    {},
                    lambda: check_draft(state.draft, rules, state.hits, failures),
                    trace,
                )
            except ToolFailure as exc:
                return _failure_output(request, state, trace, exc.tool)
            continue
        if action.action == "ask":
            trace.append({"action": "ask", "arguments": action.model_dump(mode="json"), "ok": True, "observation": {}})
            return RunOutput(input=request, result=_bare(request, "needs_input", action.message), trace=trace)
        if isinstance(action, FinishAction):
            if action.status == "completed":
                failed = _ensure_checks(state, request, rules, failures, trace)
                if isinstance(failed, str):
                    return _failure_output(request, state, trace, failed)
                problems = completion_problems(
                    state.draft,
                    state.estimate,
                    state.check,
                    state.hits,
                    request.duration_sec,
                    request.effective_style,
                )
                if problems:
                    guard_returns += 1
                    trace.append({"action": "guard", "arguments": {}, "ok": False, "observation": {"problems": problems}})
                    if guard_returns <= 1:
                        state.guard_error = "；".join(problems)
                        continue
                    message = "校验仍未通过：" + "；".join(problems)
                    trace.append({"action": "finish", "arguments": {"status": "unsatisfied", "message": message}, "ok": True, "observation": {}})
                    return RunOutput(input=request, result=_from_state(state, "unsatisfied", message), trace=trace)
                trace.append({"action": "finish", "arguments": action.model_dump(mode="json"), "ok": True, "observation": {}})
                return RunOutput(input=request, result=_from_state(state, "completed", action.message), trace=trace)
            if action.status == "no_material" and state.hits:
                state.guard_error = "已经检索到素材，不能标记为无素材"
                continue
            trace.append({"action": "finish", "arguments": action.model_dump(mode="json"), "ok": True, "observation": {}})
            return RunOutput(input=request, result=_from_state(state, action.status, action.message), trace=trace)
    message = "动作次数已用尽。"
    status = "no_material" if not state.hits else "unsatisfied"
    return RunOutput(input=request, result=_from_state(state, status, message), trace=trace)


def _ensure_checks(state: AgentState, request: Request, rules: list[Rule], failures: FailurePlan, trace: list[dict]) -> str | None:
    if state.draft is None:
        state.guard_error = "还没有草稿"
        return None
    try:
        if state.estimate is None:
            state.estimate = _call(
                "estimate",
                {},
                lambda: estimate_draft(state.draft, request.effective_style, failures),
                trace,
            )
        if state.check is None:
            state.check = _call(
                "check_rules",
                {},
                lambda: check_draft(state.draft, rules, state.hits, failures),
                trace,
            )
    except ToolFailure as exc:
        return exc.tool
    return None


def _call(tool: str, arguments: dict, fn, trace: list[dict]):
    error: ToolFailure | None = None
    for attempt in (1, 2):
        try:
            observation = fn()
            trace.append(
                {
                    "action": tool,
                    "arguments": arguments,
                    "attempt": attempt,
                    "ok": True,
                    "observation": _dump(observation),
                }
            )
            return observation
        except ToolFailure as exc:
            error = exc
            trace.append(
                {
                    "action": tool,
                    "arguments": arguments,
                    "attempt": attempt,
                    "ok": False,
                    "observation": {"error": TOOL_NAME[exc.tool]},
                }
            )
    assert error is not None
    raise error


def _same_script(left: Draft, right: Draft) -> bool:
    if left.title != right.title or len(left.shots) != len(right.shots):
        return False
    for old, new in zip(left.shots, right.shots):
        if (old.narration, old.subtitle, old.source_ids) != (new.narration, new.subtitle, new.source_ids):
            return False
    return True


def _missing_fields(request: Request) -> list[str]:
    missing: list[str] = []
    if request.theme is None or not request.theme.strip():
        missing.append("主题")
    if request.duration_sec is None or request.duration_sec <= 0:
        missing.append("目标时长")
    return missing


def _bare(request: Request, status: str, message: str) -> Result:
    return Result(status=status, message=message, risks=[])


def _failure_output(request: Request, state: AgentState, trace: list[dict], tool: str) -> RunOutput:
    message = f"工具{TOOL_NAME[tool]}失败，{TOOL_GAP[tool]}。"
    trace.append({"action": "finish", "arguments": {"status": "tool_failure", "message": message}, "ok": True, "observation": {}})
    return RunOutput(input=request, result=_from_state(state, "tool_failure", message), trace=trace)


def _from_state(state: AgentState, status: str, message: str) -> Result:
    draft = state.draft
    estimate = state.estimate
    shots: list[ShotDelivery] = []
    if draft is not None:
        timings = {item.index: item for item in estimate.shots} if estimate else {}
        for shot in draft.shots:
            timing = timings.get(shot.index)
            shots.append(
                ShotDelivery(
                    index=shot.index,
                    visual=shot.visual,
                    narration=shot.narration,
                    subtitle=shot.subtitle,
                    source_ids=list(shot.source_ids),
                    duration_sec=timing.duration_sec if timing else 0.0,
                )
            )
    source_ids: list[str] = []
    for shot in shots:
        for source_id in shot.source_ids:
            if source_id not in source_ids:
                source_ids.append(source_id)
    if not source_ids and status == "tool_failure":
        for hit in state.hits:
            source_ids.append(hit.source_id)
    risks = _risks(state.request, status, estimate, state.check)
    return Result(
        title=draft.title if draft else "",
        shots=shots,
        estimated_duration_sec=estimate.total_sec if estimate else None,
        source_ids=source_ids,
        risks=risks,
        status=status,
        message=message,
    )


def _risks(request: Request, status: str, estimate: Estimate | None, check: CheckResult | None) -> list[str]:
    if status not in {"completed", "unsatisfied", "tool_failure"}:
        return []
    risks: list[str] = []
    if not request.audience:
        risks.append("未指定受众")
    if not request.platform:
        risks.append(f"未指定平台，时长估算使用每秒 {chars_per_second(request.effective_style):g} 字")
    if not request.style:
        risks.append("未指定风格，默认口播，字幕与旁白一致")
    if status == "completed" and estimate is not None and estimate.total_ms < target_ms(request.duration_sec):
        risks.append("短于目标时长")
    if status == "completed" and check is not None:
        risks.extend(item.message for item in check.violations if not item.blocking)
    return risks


def _dump(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump(item) for item in value]
    return value
