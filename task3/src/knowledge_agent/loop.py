from knowledge_agent.guard import salvage, validate
from knowledge_agent.policy import MAX_ACTIONS
from knowledge_agent.schema import Answer, Citation, RunResult, TraceEvent
from knowledge_agent.tools import ToolError, Toolkit


def run_question(question: str, history: list[dict], toolkit: Toolkit, model) -> RunResult:
    state = {"question": question, "history": history, "observations": [], "guard_feedback": []}
    trace: list[TraceEvent] = []
    revised = False
    while len(trace) < MAX_ACTIONS:
        action = model.next_action(state)
        if action.action == "search":
            output = execute(toolkit.search, action.query or question, "search", trace, {"query": action.query})
            state["observations"].append({"action": "search", "arguments": {"query": action.query}, "output": output})
            if output.get("terminal"):
                return RunResult(answer=failure_answer("search", state["observations"]), trace=trace)
            continue
        if action.action == "read":
            if already_read(state["observations"], action.doc_id):
                output = {"ok": True, "skipped": True, "doc_id": action.doc_id, "reason": "文档已完整读取"}
                trace.append(TraceEvent(action="read", arguments={"doc_id": action.doc_id}, output=output))
                state["observations"].append({"action": "read", "arguments": {"doc_id": action.doc_id}, "output": output})
                continue
            output = execute(toolkit.read, action.doc_id or "", "read", trace, {"doc_id": action.doc_id}, question)
            state["observations"].append({"action": "read", "arguments": {"doc_id": action.doc_id}, "output": output})
            if output.get("terminal"):
                return RunResult(answer=failure_answer("read", state["observations"]), trace=trace)
            continue
        if action.action == "ask":
            answer = Answer(
                answer=action.question or "请补充作答所缺的对象或范围。",
                citations=[],
                gaps=["缺少作答所需的限定条件。"],
                status="needs_clarification",
            )
            trace.append(TraceEvent(action="ask", arguments={"question": answer.answer}, output=answer.model_dump()))
            return RunResult(answer=answer, trace=trace)
        if action.action == "finish":
            answer = action.result or Answer(answer="", citations=[], gaps=["没有形成回答。"], status="insufficient_evidence")
            errors = validate(answer, state["observations"])
            trace.append(
                TraceEvent(action="finish", arguments={"reason": action.reason}, output={"answer": answer.model_dump(), "errors": errors})
            )
            if errors and not revised:
                revised = True
                state["guard_feedback"] = errors
                continue
            if errors:
                answer = salvage(answer, state["observations"])
            return RunResult(answer=answer, trace=trace)
        trace.append(TraceEvent(action=action.action, arguments={}, output={"ok": False, "error": "未知动作"}))
    from knowledge_agent.policy import decide

    answer = decide(state)
    errors = validate(answer, state["observations"])
    if errors:
        answer = salvage(answer, state["observations"])
    trace.append(TraceEvent(action="finish", arguments={"reason": "达到轮数上限"}, output=answer.model_dump()))
    return RunResult(answer=answer, trace=trace)


def execute(method, argument: str, tool: str, trace: list[TraceEvent], arguments: dict, query: str = "") -> dict:
    output = attempt(method, argument, tool, query)
    trace.append(TraceEvent(action=tool, arguments=arguments, output=public_output(output)))
    if output.get("ok"):
        return output
    output = attempt(method, argument, tool, query)
    trace.append(TraceEvent(action=tool, arguments=arguments, output=public_output(output)))
    if output.get("ok"):
        return output
    output["terminal"] = True
    return output


def attempt(method, argument: str, tool: str, query: str) -> dict:
    try:
        if tool == "read":
            return method(argument, query)
        return method(argument)
    except ToolError as error:
        return {"ok": False, "tool": tool, "error": error.message}


def public_output(output: dict) -> dict:
    return {key: value for key, value in output.items() if key != "terminal"}


def already_read(observations: list[dict], doc_id: str | None) -> bool:
    for item in observations:
        output = item.get("output") or {}
        if item["action"] == "read" and output.get("doc_id") == doc_id and output.get("found") and not output.get("truncated"):
            return True
    return False


def failure_answer(tool: str, observations: list[dict]) -> Answer:
    citations = []
    for item in observations:
        output = item.get("output") or {}
        if item["action"] == "search" and output.get("ok"):
            for candidate in output.get("candidates", []):
                excerpt = candidate.get("excerpt") or ""
                if excerpt:
                    citations.append(
                        Citation(doc_id=candidate["doc_id"], version_date=candidate.get("version_date"), excerpt=excerpt)
                    )
        if item["action"] == "read" and output.get("found") and output.get("text"):
            citations.append(
                Citation(doc_id=output["doc_id"], version_date=output.get("version_date"), excerpt=output["text"][:180])
            )
    name = "检索" if tool == "search" else "片段读取"
    return Answer(
        answer=f"{name}工具失败，本次未能完成核实。这表示工具没有成功返回结果，不是资料库中没有相关内容。",
        citations=citations,
        gaps=[f"{name}失败，相关内容未能完成核实。"],
        status="tool_failure",
    )
