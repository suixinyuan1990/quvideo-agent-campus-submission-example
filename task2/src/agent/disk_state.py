"""把一次运行的状态写到 data/state，供下一次命令沿用或续跑。"""

from __future__ import annotations

import copy

from src.agent.files import ROOT, dump_json, load_json


def state_path(case_id: str):
    return ROOT / "data" / "state" / f"{case_id}.json"


def load_state(case_id: str) -> dict | None:
    path = state_path(case_id)
    if not path.exists():
        return None
    return copy.deepcopy(load_json(path))


def save_state(case_id: str, store: dict) -> None:
    dump_json(state_path(case_id), copy.deepcopy(store))


def clear_state(case_id: str) -> None:
    path = state_path(case_id)
    if path.exists():
        path.unlink()
