"""Turn AdvertiseGen JSONL into citable product materials.

`body` is the original attribute string and the only product fact.
`reference_summaries.jsonl` keeps the published ad copy. That copy is not a material.
"""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATASET = "shibing624/AdvertiseGen"
SOURCE_URL = "https://huggingface.co/datasets/shibing624/AdvertiseGen"
SPLITS = ("train", "dev")
EXTRA_NUMBER = re.compile(r"\d+(?:\.\d+)?%|\d+(?:\.\d+)?倍")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def attributes_of(content: str) -> list[dict[str, str]]:
    pairs = []
    for part in content.split("*"):
        if "#" not in part:
            raise ValueError(f"attribute is missing '#': {content}")
        key, value = part.split("#", 1)
        if not key or not value:
            raise ValueError(f"empty attribute key or value: {content}")
        pairs.append({"key": key, "value": value})
    if not pairs:
        raise ValueError(f"no attributes: {content}")
    return pairs


def main() -> None:
    documents = ROOT / "documents.jsonl"
    summaries = ROOT / "reference_summaries.jsonl"
    manifest_path = ROOT / "manifest.json"
    files = {}
    document_count = 0
    single_attribute = 0
    extra_numbers = 0
    unk_summaries = 0

    with documents.open("w", encoding="utf-8", newline="\n") as doc_out, summaries.open(
        "w", encoding="utf-8", newline="\n"
    ) as summary_out:
        for split in SPLITS:
            source = ROOT / f"{split}.json"
            rows = 0
            for line in source.open(encoding="utf-8"):
                if not line.strip():
                    continue
                rows += 1
                record = json.loads(line)
                content = record["content"]
                summary = record["summary"]
                pairs = attributes_of(content)
                source_id = f"AG-{split}-{rows:06d}"
                if len(pairs) == 1:
                    single_attribute += 1
                extras = [token for token in EXTRA_NUMBER.findall(summary) if token not in content]
                if extras:
                    extra_numbers += 1
                if "<UNK>" in summary:
                    unk_summaries += 1
                doc_out.write(
                    json.dumps(
                        {
                            "source_id": source_id,
                            "split": split,
                            "row_index": rows,
                            "body": content,
                            "attributes": pairs,
                            "dataset": DATASET,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                summary_out.write(
                    json.dumps(
                        {
                            "source_id": source_id,
                            "reference_summary": summary,
                            "citable": False,
                            "dataset": DATASET,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                document_count += 1
            files[f"{split}.json"] = {
                "sha256": sha256(source),
                "bytes": source.stat().st_size,
                "rows": rows,
            }

    manifest = {
        "dataset": DATASET,
        "source_url": SOURCE_URL,
        "documents": document_count,
        "single_attribute_documents": single_attribute,
        "summaries_with_number_absent_from_body": extra_numbers,
        "summaries_with_unk": unk_summaries,
        "files": files,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
