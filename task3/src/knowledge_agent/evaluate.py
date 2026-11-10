import argparse
import json
import random
import re
from pathlib import Path

from knowledge_agent.corpus import Corpus, Document
from knowledge_agent.loop import run_question
from knowledge_agent.model import ScriptedModel
from knowledge_agent.tools import Toolkit

SAMPLE_SEED = 20260310
SAMPLE_SIZE = 20


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def mentioned(text: str, phrase: str) -> bool:
    if re.search(r"[A-Za-z0-9]", phrase):
        return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, flags=re.IGNORECASE) is not None
    return phrase.casefold() in text.casefold()


def evaluate_task(task: dict, documents: dict[str, dict]) -> dict:
    corpus = Corpus([Document.model_validate(documents[doc_id]) for doc_id in task["retrieved_doc_ids"]])
    result = run_question(task["question"], [], Toolkit(corpus), ScriptedModel())
    answer = result.answer
    errors = check_task(task, documents, answer)
    return {
        "task_id": task["task_id"],
        "scenario": task["scenario"],
        "passed": not errors,
        "errors": errors,
        "output": answer.model_dump(),
        "trace": [event.model_dump() for event in result.trace],
    }


def check_task(task: dict, documents: dict[str, dict], answer) -> list[str]:
    errors = []
    if answer.status != task["expected_status"]:
        errors.append(f"状态是 {answer.status}，期望 {task['expected_status']}")
    cited = {citation.doc_id for citation in answer.citations}
    missing = [doc_id for doc_id in task["must_cite_doc_ids"] if doc_id not in cited]
    if missing:
        errors.append(f"缺少引用 {missing}")
    for citation in answer.citations:
        body = documents[citation.doc_id]["body"]
        if citation.excerpt not in body:
            errors.append(f"{citation.doc_id} 的引用不在正文中")
    if task["scenario"] == "document_conflict":
        text = answer.answer
        forbidden = task["forbidden_sole_answers"]
        hits = [mentioned(text, phrase) for phrase in forbidden]
        cited_both = set(task["must_cite_doc_ids"]).issubset(cited)
        if any(hits) and not all(hits) and not cited_both:
            errors.append("只采纳了冲突中的一个答案")
        if not re.search(r"confirm|确认", text, flags=re.IGNORECASE):
            errors.append("没有请求确认适用文档")
    if task["scenario"] == "single_document":
        if cited - set(task["must_cite_doc_ids"]):
            errors.append("引用了检索池以外的文档")
        if answer.gaps:
            errors.append("单文档作答应没有资料缺口")
        doc_id = task["must_cite_doc_ids"][0]
        body = documents[doc_id]["body"]
        expected = task["expected_answer"]
        combined = answer.answer + "\n" + "\n".join(citation.excerpt for citation in answer.citations)
        if expected.casefold() in body.casefold() and expected.casefold() not in combined.casefold():
            errors.append("回答没有覆盖文档支持的答案")
    return errors


def sample_tasks(tasks: list[dict], size: int = SAMPLE_SIZE, seed: int = SAMPLE_SEED) -> list[dict]:
    conflicts = [task for task in tasks if task["scenario"] == "document_conflict"]
    singles = [task for task in tasks if task["scenario"] == "single_document"]
    rng = random.Random(seed)
    rng.shuffle(conflicts)
    rng.shuffle(singles)
    return conflicts[:size] + singles[:size]


def evaluate_file(tasks_path: Path, documents_path: Path, size: int = SAMPLE_SIZE, seed: int = SAMPLE_SEED) -> dict:
    documents = {row["doc_id"]: row for row in load_rows(documents_path)}
    chosen = sample_tasks(load_rows(tasks_path), size, seed)
    results = [evaluate_task(task, documents) for task in chosen]
    return {
        "seed": seed,
        "sample_size_per_scenario": size,
        "total": len(results),
        "passed": sum(item["passed"] for item in results),
        "results": results,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="评测限定检索池中的问答")
    parser.add_argument("--tasks", default="data/faitheval-inconsistent/tasks.jsonl")
    parser.add_argument("--documents", default="data/faitheval-inconsistent/documents.jsonl")
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=SAMPLE_SEED)
    parser.add_argument("--output", default="examples/faitheval-sample/summary.json")
    args = parser.parse_args(argv)
    report = evaluate_file(Path(args.tasks), Path(args.documents), args.sample_size, args.seed)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['passed']}/{report['total']} passed, seed {report['seed']}")
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
