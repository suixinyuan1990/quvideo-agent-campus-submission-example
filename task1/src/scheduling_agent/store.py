"""排期草稿存储。只保存草稿，没有任何发布记录。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scheduling_agent.catalog import dump_json, load_json


class DraftStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.drafts: list[dict[str, Any]] = []
        if self.path.exists():
            payload = load_json(self.path)
            self.drafts = list(payload.get("drafts", []))

    def count(self) -> int:
        return len(self.drafts)

    def list_drafts(self) -> list[dict[str, Any]]:
        return list(self.drafts)

    def find(self, draft_id: str) -> dict[str, Any] | None:
        for item in self.drafts:
            if item["draft_id"] == draft_id:
                return item
        return None

    def add(self, draft: dict[str, Any]) -> None:
        self.drafts.append(draft)
        self.save()

    def save(self) -> None:
        dump_json(self.path, {"drafts": self.drafts})
