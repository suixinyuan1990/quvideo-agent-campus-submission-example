from knowledge_agent.schema import Answer


def validate(answer: Answer, observations: list[dict]) -> list[str]:
    errors: list[str] = []
    evidence = evidence_text(observations)
    for citation in answer.citations:
        allowed = evidence.get(citation.doc_id, "")
        if citation.excerpt not in allowed:
            errors.append(f"{citation.doc_id} 的引用不是本轮工具返回的连续原文")
        version = evidence_version(observations, citation.doc_id)
        if version is not None and citation.version_date != version:
            errors.append(f"{citation.doc_id} 的版本日期与资料不一致")
    if answer.status == "answered":
        if answer.gaps:
            errors.append("answered 时资料缺口必须为空")
        if not answer.citations:
            errors.append("answered 时至少要有一条引用")
    if answer.status == "insufficient_evidence" and not evidence and answer.citations:
        errors.append("没有相关材料时引用必须为空")
    if answer.status == "insufficient_evidence" and not answer.gaps:
        errors.append("证据不足时要写明资料缺口")
    if answer.status == "conflict":
        cited = {citation.doc_id for citation in answer.citations}
        if len(cited) < 2:
            errors.append("conflict 时至少要引用两份文档")
        gap_text = " ".join(answer.gaps).lower()
        if "效力" not in gap_text and "precedence" not in gap_text:
            errors.append("conflict 时缺口要写明缺少效力规则")
    if answer.status == "tool_failure":
        text = answer.answer.lower()
        if "失败" not in answer.answer and "fail" not in text:
            errors.append("工具失败时回答要说明核实失败")
    if answer.status in {"conflict", "needs_clarification"} and not answer.answer.strip():
        errors.append("需要确认时回答不能为空")
    return errors


def salvage(answer: Answer, observations: list[dict]) -> Answer:
    evidence = evidence_text(observations)
    versions = {doc_id: evidence_version(observations, doc_id) for doc_id in evidence}
    kept = []
    for citation in answer.citations:
        if citation.excerpt and citation.excerpt in evidence.get(citation.doc_id, ""):
            version = versions.get(citation.doc_id)
            kept.append(citation.model_copy(update={"version_date": version}))
    gaps = list(answer.gaps)
    gaps.append("结果未能满足引用约束。")
    return answer.model_copy(update={"citations": kept, "gaps": gaps, "status": "insufficient_evidence"})


def evidence_text(observations: list[dict]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for item in observations:
        output = item.get("output") or {}
        if not output.get("ok"):
            continue
        if item["action"] == "read" and output.get("found") and output.get("text"):
            texts[output["doc_id"]] = texts.get(output["doc_id"], "") + output["text"]
        if item["action"] == "search":
            for candidate in output.get("candidates", []):
                texts[candidate["doc_id"]] = texts.get(candidate["doc_id"], "") + candidate.get("excerpt", "")
    return texts


def evidence_version(observations: list[dict], doc_id: str) -> str | None:
    for item in observations:
        output = item.get("output") or {}
        if item["action"] == "read" and output.get("doc_id") == doc_id and "version_date" in output:
            return output.get("version_date")
        if item["action"] == "search":
            for candidate in output.get("candidates", []):
                if candidate["doc_id"] == doc_id:
                    return candidate.get("version_date")
    return None
