"""读取合成资料。运行时草稿不写回这里。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class DataCatalog:
    def __init__(self, data_dir: str | Path):
        root = Path(data_dir)
        self.root = root
        self.materials: dict[str, dict[str, Any]] = load_json(root / "materials.json")
        self.rules: dict[str, Any] = load_json(root / "rules.json")
        self.slots: dict[str, dict[str, Any]] = load_json(root / "slots.json")
        supplements = root / "supplements.json"
        faults = root / "tool_faults.json"
        self.supplements: dict[str, dict[str, Any]] = load_json(supplements) if supplements.exists() else {}
        self.faults: dict[str, list[dict[str, Any]]] = load_json(faults) if faults.exists() else {}
