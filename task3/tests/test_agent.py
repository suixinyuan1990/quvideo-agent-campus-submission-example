import json
from pathlib import Path

from knowledge_agent.corpus import Corpus
from knowledge_agent.evaluate import evaluate_file
from knowledge_agent.loop import run_question
from knowledge_agent.model import ScriptedModel
from knowledge_agent.schema import Action, Answer, Citation
from knowledge_agent.tools import Toolkit

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ROOT / "data" / "policies" / "documents.jsonl"
EXAMPLES = ROOT / "examples" / "scenarios"


def run(question: str, history: list[dict] | None = None, failures: dict[str, int] | None = None):
    corpus = Corpus.load(POLICIES)
    result = run_question(question, history or [], Toolkit(corpus, failures), ScriptedModel())
    return result


def save(name: str, question: str, history: list[dict], result) -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    payload = {
        "input": {"question": question, "history": history},
        "output": result.answer.model_dump(),
        "trace": [event.model_dump() for event in result.trace],
    }
    (EXAMPLES / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_clear_answer_and_paraphrase():
    question = "入职满一年的员工每年有多少天带薪年假？"
    paraphrase = "干满一年后，每年的带薪年假是几天？"
    first = run(question)
    second = run(paraphrase)
    save("clear-answer", question, [], first)
    save("paraphrase", paraphrase, [], second)
    for result in (first, second):
        assert result.answer.status == "answered"
        assert result.answer.gaps == []
        assert result.answer.citations[0].doc_id == "POL-LEAVE-001"
        assert result.answer.citations[0].version_date == "2024-03-01"
        assert result.answer.citations[0].excerpt in Corpus.load(POLICIES).by_id["POL-LEAVE-001"].body
        assert "10" in result.answer.answer
    assert [event.action for event in first.trace].count("search") == 1


def test_document_conflict_keeps_both_policies():
    question = "报销期限多久？"
    result = run(question)
    save("conflict", question, [], result)
    answer = result.answer
    assert answer.status == "conflict"
    assert {item.doc_id for item in answer.citations} == {"POL-EXP-D01", "POL-EXP-D02"}
    assert "30" in answer.answer and "15" in answer.answer
    assert "确认" in answer.answer
    assert any("效力" in gap for gap in answer.gaps)
    assert "不能单独" in answer.answer
    assert any(event.action == "read" for event in result.trace)
    corpus = Corpus.load(POLICIES)
    for citation in answer.citations:
        assert citation.excerpt in corpus.by_id[citation.doc_id].body


def test_conflict_retrieval_returns_both_documents():
    corpus = Corpus.load(POLICIES)
    candidates = Toolkit(corpus).search("报销期限多久？")["candidates"]
    assert {item["doc_id"] for item in candidates} >= {"POL-EXP-D01", "POL-EXP-D02"}


def test_refuses_when_documents_do_not_contain_the_fact():
    questions = [
        "报销需要附上发票吗？",
        "年假能不能结转到下一年？",
        "远程协作工具怎么预约会议室？",
        "试用期工资是多少？",
    ]
    for question in questions:
        result = run(question)
        save(f"refuse-{question[:8]}", question, [], result)
        assert result.answer.status == "insufficient_evidence"
        assert result.answer.citations == []
        assert "不能回答" in result.answer.answer


def test_question_outside_corpus():
    question = "公司班车今晚几点发车？"
    result = run(question)
    save("outside-corpus", question, [], result)
    assert result.answer.status == "insufficient_evidence"
    assert result.answer.citations == []
    assert result.answer.gaps
    assert "班车" not in result.answer.answer or "不能回答" in result.answer.answer


def test_follow_up_uses_history():
    history = [
        {"role": "user", "content": "年假制度怎么规定？"},
        {"role": "assistant", "content": "入职满一年的员工每年享有 10 天带薪年假。"},
    ]
    question = "那试用期呢？"
    result = run(question, history)
    save("follow-up", question, history, result)
    assert result.answer.status == "answered"
    assert result.answer.citations[0].doc_id == "POL-LEAVE-PROB"
    assert "0.5" in result.answer.answer
    assert result.answer.gaps == []


def test_tool_failure_is_not_treated_as_missing_document():
    question = "报销期限多久？"
    result = run(question, failures={"read": 2})
    save("tool-failure", question, [], result)
    assert result.answer.status == "tool_failure"
    assert "失败" in result.answer.answer
    assert "不是资料库中没有" in result.answer.answer
    assert result.answer.citations
    reads = [event for event in result.trace if event.action == "read"]
    assert len(reads) == 2
    assert all(event.output and event.output.get("ok") is False for event in reads)


def test_guard_rejects_invented_excerpt_once_then_salvages():
    corpus = Corpus.load(POLICIES)
    bad = Answer(
        answer="报销期限为 15 天。",
        citations=[Citation(doc_id="POL-EXP-D02", version_date="2024-01-15", excerpt="这句话不在原文里")],
        gaps=[],
        status="answered",
    )
    good = Answer(
        answer="根据 POL-EXP-D02，报销期限为 15 天。",
        citations=[Citation(doc_id="POL-EXP-D02", version_date="2024-01-15", excerpt="报销期限为 15 天。")],
        gaps=[],
        status="answered",
    )

    class TwoStep:
        def __init__(self):
            self.calls = 0

        def next_action(self, state):
            self.calls += 1
            if self.calls == 1:
                return Action(action="search", query="报销期限")
            if state["guard_feedback"]:
                return Action(action="finish", result=good, reason="修正引用")
            return Action(action="finish", result=bad, reason="第一次")

    result = run_question("报销期限多久？", [], Toolkit(corpus), TwoStep())
    assert result.answer.status == "answered"
    assert result.answer.citations[0].excerpt == "报销期限为 15 天。"


def test_faitheval_sample():
    report = evaluate_file(
        ROOT / "data" / "faitheval-inconsistent" / "tasks.jsonl",
        ROOT / "data" / "faitheval-inconsistent" / "documents.jsonl",
    )
    output = ROOT / "examples" / "faitheval-sample" / "summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed = [item for item in report["results"] if not item["passed"]]
    assert report["passed"] == report["total"], failed[:3]
