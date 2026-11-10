"""Turn FaithEval inconsistent rows into document and task files.

The published context is two passages joined as "Document: ... Document: ...".
Neither passage states a scope or a priority. D01 supports answers[0].
D02 supports answers[1].
"""

import hashlib
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
PARQUET = ROOT / "test-00000-of-00001.parquet"
SPLIT = re.compile(r"(?:(?<=^)|(?<=\s))Document:\s+")
DATASET = "Salesforce/FaithEval-inconsistent-v1.0"


def main() -> None:
    frame = pd.read_parquet(PARQUET)
    documents = []
    tasks = []
    answer_missing = 0
    for record in frame.to_dict("records"):
        parts = [part.strip() for part in SPLIT.split(record["context"]) if part.strip()]
        if len(parts) != 2:
            raise ValueError(f"{record['qid']} did not split into two documents")
        answers = [str(answer) for answer in record["answers"]]
        if len(answers) != 2 or answers[0].casefold() == answers[1].casefold():
            raise ValueError(f"{record['qid']} does not have two different answers")
        doc_ids = [f"FE-{record['qid']}-D01", f"FE-{record['qid']}-D02"]
        answer_in_body = []
        for role, doc_id, body, answer in zip(("D01", "D02"), doc_ids, parts, answers):
            present = answer.casefold() in body.casefold()
            answer_in_body.append(present)
            if not present:
                answer_missing += 1
            documents.append(
                {
                    "doc_id": doc_id,
                    "version_date": None,
                    "doc_type": "passage",
                    "scope": None,
                    "priority": None,
                    "role": role,
                    "body": body,
                    "supported_answer": answer,
                    "answer_in_body": present,
                    "source_qid": record["qid"],
                    "source_subset": record["subset"],
                    "dataset": DATASET,
                }
            )
        tasks.append(
            {
                "task_id": f"{record['qid']}-conflict",
                "scenario": "document_conflict",
                "derived": False,
                "question": record["question"],
                "retrieved_doc_ids": doc_ids,
                "expected_status": "conflict",
                "must_cite_doc_ids": doc_ids,
                "conflicting_answers": answers,
                "answers_in_body": answer_in_body,
                "forbidden_sole_answers": answers,
                "must_request_applicable_document": True,
                "scope": None,
                "priority": None,
                "source_qid": record["qid"],
                "source_subset": record["subset"],
                "dataset": DATASET,
            }
        )
        tasks.append(
            {
                "task_id": f"{record['qid']}-only-d01",
                "scenario": "single_document",
                "derived": True,
                "question": record["question"],
                "retrieved_doc_ids": [doc_ids[0]],
                "expected_status": "answered",
                "expected_answer": answers[0],
                "must_cite_doc_ids": [doc_ids[0]],
                "scope": None,
                "priority": None,
                "source_qid": record["qid"],
                "source_subset": record["subset"],
                "dataset": DATASET,
            }
        )
    write_jsonl(ROOT / "documents.jsonl", documents)
    write_jsonl(ROOT / "tasks.jsonl", tasks)
    digest = hashlib.sha256(PARQUET.read_bytes()).hexdigest()
    manifest = {
        "dataset": DATASET,
        "source_url": "https://huggingface.co/datasets/Salesforce/FaithEval-inconsistent-v1.0",
        "source_file": PARQUET.name,
        "source_sha256": digest,
        "source_rows": len(frame),
        "documents": len(documents),
        "tasks": len(tasks),
        "conflict_tasks": sum(task["scenario"] == "document_conflict" for task in tasks),
        "single_document_tasks": sum(task["scenario"] == "single_document" for task in tasks),
        "supported_answer_not_exact_substring": answer_missing,
    }
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
