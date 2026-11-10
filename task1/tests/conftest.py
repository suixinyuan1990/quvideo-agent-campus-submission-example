from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    shutil.copytree(REPO / "data", data)
    return data, tmp_path / "drafts.json"
