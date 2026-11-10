"""把 examples/*/input.json 跑成实际输出和 trace。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from scheduling_agent.agent import run_input
from scheduling_agent.catalog import dump_json, load_json
from scheduling_agent.model import ObservationDecisionModel

ROOT = Path(__file__).resolve().parents[2]

CASES = (
    "01-normal",
    "02-missing-info",
    "03-rule-risk",
    "04-slot-conflict",
    "05-duplicate-submit",
    "06-save-failure",
    "07-tool-failure",
    "08-step-limit",
    "09-tool-call-limit",
    "10-confirmed-alternative",
    "11-transient-then-schedule",
)


def generate(output_root: Path | None = None) -> None:
    target = output_root or (ROOT / "examples")
    data_dir = ROOT / "data"
    model = ObservationDecisionModel()
    for case in CASES:
        payload = load_json(ROOT / "examples" / case / "input.json")
        with tempfile.TemporaryDirectory() as tmp:
            bundle = run_input(
                payload,
                data_dir=data_dir,
                store_path=Path(tmp) / "drafts.json",
                model=model,
            )
        destination = target / case
        destination.mkdir(parents=True, exist_ok=True)
        dump_json(destination / "output.json", bundle["output"])
        dump_json(destination / "trace.json", bundle["trace"])


def main() -> None:
    generate()


if __name__ == "__main__":
    main()
