import json
import re
from pathlib import Path

from knowledge_agent.corpus import Corpus
from knowledge_agent.loop import run_question
from knowledge_agent.model import ScriptedModel
from knowledge_agent.tools import Toolkit

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ROOT / "data" / "policies" / "documents.jsonl"
REPORT = ROOT / "examples" / "audit" / "report.json"


def run(corpus: Corpus, question: str, history: list | None = None):
    return run_question(question, history or [], Toolkit(corpus), ScriptedModel())


def edited(corpus: Corpus, updates: dict[str, str]) -> Corpus:
    documents = []
    for document in corpus.documents:
        if document.doc_id in updates:
            documents.append(document.model_copy(update={"body": updates[document.doc_id]}))
        else:
            documents.append(document)
    return Corpus(documents)


def trace_actions(result) -> list[str]:
    return [event.action for event in result.trace]


def cited_text(result) -> str:
    return "\n".join(citation.excerpt for citation in result.answer.citations)


def excerpts_are_verbatim(result, corpus: Corpus) -> bool:
    for citation in result.answer.citations:
        document = corpus.by_id.get(citation.doc_id)
        if document is None or citation.excerpt not in document.body:
            return False
    return True


def answer_facts_supported(result) -> bool:
    """Policy facts stated as the conclusion must occur in a cited excerpt."""
    if result.answer.status == "insufficient_evidence":
        return result.answer.citations == [] and "不能回答" in result.answer.answer
    if result.answer.status == "tool_failure":
        return "失败" in result.answer.answer and "不是资料库中没有" in result.answer.answer
    excerpts = cited_text(result)
    if result.answer.status == "conflict":
        claims = re.findall(r"报销期限为 \d+ 天", result.answer.answer)
        return len(claims) >= 2 and len(set(claims)) >= 2 and all(claim in excerpts for claim in claims)
    claim = result.answer.answer.split("，", 1)[-1]
    return bool(claim) and claim in excerpts


def test_audit_against_citation_and_replacement_standard():
    corpus = Corpus.load(POLICIES)
    history = [
        {"role": "user", "content": "年假制度怎么规定？"},
        {"role": "assistant", "content": "入职满一年的员工每年享有 10 天带薪年假。"},
    ]
    baseline_questions = {
        "clear": ("入职满一年的员工每年有多少天带薪年假？", []),
        "paraphrase": ("干满一年后，每年的带薪年假是几天？", []),
        "conflict": ("报销期限多久？", []),
        "outside": ("公司班车今晚几点发车？", []),
        "follow_up": ("那试用期呢？", history),
    }
    baseline = {}
    for name, (question, turns) in baseline_questions.items():
        result = run(corpus, question, turns)
        baseline[name] = {
            "status": result.answer.status,
            "answer": result.answer.answer,
            "actions": trace_actions(result),
            "verbatim": excerpts_are_verbatim(result, corpus),
            "supported": answer_facts_supported(result),
        }
    failure = run(corpus, "报销期限多久？")
    # The shared helper has no failure injection; rerun with a failing reader.
    failure = run_question("报销期限多久？", [], Toolkit(corpus, {"read": 2}), ScriptedModel())
    baseline["tool_failure"] = {
        "status": failure.answer.status,
        "answer": failure.answer.answer,
        "actions": trace_actions(failure),
        "verbatim": excerpts_are_verbatim(failure, corpus),
        "supported": answer_facts_supported(failure),
    }

    leave = "入职满一年的员工每年有多少天带薪年假？"
    original_leave = run(corpus, leave)
    replaced_days = edited(corpus, {"POL-LEAVE-001": corpus.by_id["POL-LEAVE-001"].body.replace("10 天", "12 天")})
    days = run(replaced_days, leave)
    removed = edited(corpus, {"POL-LEAVE-001": "食堂菜单。工作日午餐供应两荤一素。"})
    removed_result = run(removed, leave)
    same = "报销期限。报销期限为 20 天。费用发生后 20 天内提交报销申请。逾期申请不予受理。"
    aligned = edited(corpus, {"POL-EXP-D01": same, "POL-EXP-D02": same})
    aligned_result = run(aligned, "报销期限多久？")
    only_d02 = edited(corpus, {"POL-EXP-D01": "食堂菜单。工作日午餐供应两荤一素。"})
    only_result = run(only_d02, "报销期限多久？")
    original_conflict = run(corpus, "报销期限多久？")

    typo_query = "带薪年假如天"
    bm25_ids = [doc_id for doc_id, _score in corpus.bm25_hits(typo_query, 5)]
    fused_ids = [item["doc_id"] for item in Toolkit(corpus).search(typo_query)["candidates"]]
    conflict_fused = [item["doc_id"] for item in Toolkit(corpus).search("报销期限多久？")["candidates"]]

    critical = []
    if removed_result.answer.status != "insufficient_evidence" or removed_result.answer.citations:
        critical.append("删除满一年条款后，仍用其他制度回答了满一年员工的问题。")
    if aligned_result.answer.status != "answered" or "20" not in aligned_result.answer.answer or "冲突" in aligned_result.answer.answer:
        critical.append("两份报销制度改成相同的 20 天后，没有按这一规定作答。")

    report = {
        "baseline": baseline,
        "replacement": {
            "ten_to_twelve": {
                "answer_changed": original_leave.answer.answer != days.answer.answer,
                "actions_changed": trace_actions(original_leave) != trace_actions(days),
                "answer": days.answer.answer,
                "actions": trace_actions(days),
                "supported": "12 天" in days.answer.answer and "12 天" in cited_text(days),
            },
            "remove_annual_leave_rule": {
                "answer_changed": original_leave.answer.answer != removed_result.answer.answer,
                "actions_changed": trace_actions(original_leave) != trace_actions(removed_result),
                "status": removed_result.answer.status,
                "answer": removed_result.answer.answer,
                "actions": trace_actions(removed_result),
            },
            "align_reimbursement": {
                "answer_changed": original_conflict.answer.answer != aligned_result.answer.answer,
                "actions_changed": trace_actions(original_conflict) != trace_actions(aligned_result),
                "status": aligned_result.answer.status,
                "answer": aligned_result.answer.answer,
                "actions": trace_actions(aligned_result),
            },
            "remove_d01": {
                "answer_changed": original_conflict.answer.status != only_result.answer.status,
                "actions_changed": trace_actions(original_conflict) != trace_actions(only_result),
                "status": only_result.answer.status,
                "answer": only_result.answer.answer,
                "actions": trace_actions(only_result),
                "supported": "15 天" in only_result.answer.answer and "15 天" in cited_text(only_result),
            },
        },
        "retrieval": {
            "bm25": bm25_ids,
            "fused": fused_ids,
            "conflict_fused": conflict_fused,
            "precision_improved": bm25_ids == ["POL-LEAVE-001", "POL-LEAVE-PROB"] and fused_ids == ["POL-LEAVE-001"],
            "conflict_pair_kept": set(conflict_fused) >= {"POL-EXP-D01", "POL-EXP-D02"},
        },
        "critical_defects": critical,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    assert all(item["verbatim"] and item["supported"] for item in baseline.values())
    assert report["replacement"]["ten_to_twelve"]["supported"]
    assert report["replacement"]["remove_d01"]["supported"]
    assert report["retrieval"]["precision_improved"]
    assert report["retrieval"]["conflict_pair_kept"]
    assert critical == []
