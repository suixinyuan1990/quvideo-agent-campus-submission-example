from __future__ import annotations

import json
from pathlib import Path

from scheduling_agent.build_examples import CASES, generate

REPO = Path(__file__).resolve().parents[1]


def test_committed_examples_match_a_fresh_run(tmp_path: Path) -> None:
    generate(tmp_path)
    for case in CASES:
        for name in ("output.json", "trace.json"):
            fresh = json.loads((tmp_path / case / name).read_text(encoding="utf-8"))
            committed = json.loads((REPO / "examples" / case / name).read_text(encoding="utf-8"))
            assert fresh == committed
