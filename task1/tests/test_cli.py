from __future__ import annotations

import json

from scheduling_agent.cli import main


def test_cli_writes_conflict_case(tmp_path, capsys) -> None:
    store = tmp_path / "drafts.json"
    output = tmp_path / "output.json"
    trace = tmp_path / "trace.json"
    code = main(
        [
            "examples/04-slot-conflict/input.json",
            "--store",
            str(store),
            "--output",
            str(output),
            "--trace",
            str(trace),
        ]
    )
    assert code == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["suggested_slot"] == "19:00"
    assert result["publish_state"] == "not_published"
    assert result["draft_save_status"] == "saved"
    captured = capsys.readouterr()
    assert captured.out == ""

    again = main(["examples/04-slot-conflict/input.json", "--store", str(store)])
    assert again == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["draft_save_status"] == "duplicate"
    assert printed["draft_id"] == result["draft_id"]


def test_cli_save_failure_exit_code(tmp_path, capsys) -> None:
    code = main(["examples/06-save-failure/input.json", "--store", str(tmp_path / "drafts.json")])
    assert code == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["draft_save_status"] == "failed"


def test_cli_limit_exit_code(tmp_path, capsys) -> None:
    code = main(["examples/08-step-limit/input.json", "--store", str(tmp_path / "drafts.json")])
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_status"] == "incomplete"
