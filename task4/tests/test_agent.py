import json
from pathlib import Path

from script_agent.corpus import Corpus
from script_agent.loop import run
from script_agent.rules import load_rules
from script_agent.schema import Request, RunOutput
from script_agent.textutil import spoken_count
from script_agent.tools import FailurePlan

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "fixtures"
SCENARIOS = ROOT / "examples" / "scenarios"
DISCLAIMER = "本视频仅介绍已列出的功能，具体以产品说明为准。"


def _run(name: str, request: Request, rules: str | None = None, failures: dict | None = None) -> RunOutput:
    output = run(
        request,
        Corpus.load(FIXTURES / "materials.jsonl"),
        load_rules(FIXTURES / rules) if rules else [],
        failures=FailurePlan(failures),
    )
    SCENARIOS.mkdir(parents=True, exist_ok=True)
    destination = SCENARIOS / f"{name}.json"
    destination.write_text(
        json.dumps(output.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def _full(**overrides) -> Request:
    data = {
        "theme": "介绍支持字幕",
        "duration_sec": 30,
        "audience": "功能介绍观众",
        "platform": "抖音",
        "style": "口播",
    }
    data.update(overrides)
    return Request(**data)


def test_normal_generation_cites_p01_without_invented_numbers():
    output = _run("normal", _full())
    result = output.result
    assert result.status == "completed"
    assert result.source_ids == ["P01"]
    assert result.estimated_duration_sec == 2.0
    assert result.estimated_duration_sec <= 30
    assert "支持字幕" in result.shots[0].narration
    assert "80%" not in result.shots[0].narration
    assert "短于目标时长" in result.risks
    assert result.title
    assert result.shots[0].visual
    assert not any(item["action"] == "search" and item["observation"] == [] for item in output.trace)


def test_missing_theme_and_duration_ask_before_search():
    missing_theme = _run("missing-theme", _full(theme=None))
    assert missing_theme.result.status == "needs_input"
    assert "主题" in missing_theme.result.message
    assert not any(item["action"] == "search" for item in missing_theme.trace)

    missing_duration = _run("missing-duration", _full(duration_sec=None))
    assert missing_duration.result.status == "needs_input"
    assert "目标时长" in missing_duration.result.message
    assert not any(item["action"] == "search" for item in missing_duration.trace)

    vague = _run("vague-theme", _full(theme="做一个视频"))
    assert vague.result.status == "needs_input"
    assert "主题" in vague.result.message
    assert not any(item["action"] == "search" for item in vague.trace)


def test_no_material_rewrites_once_then_stops():
    output = _run("no-material", _full(theme="运动鞋气垫"))
    searches = [item for item in output.trace if item["action"] == "search"]
    assert [item["arguments"]["query"] for item in searches] == ["运动鞋气垫", "运动鞋"]
    assert all(item["observation"] == [] for item in searches)
    assert output.result.status == "no_material"
    assert output.result.source_ids == []
    assert output.result.shots == []


def test_tool_failure_is_distinct_from_empty_search():
    search_failed = _run("tool-failure-search", _full(), failures={"search": 2})
    search_attempts = [item for item in search_failed.trace if item["action"] == "search"]
    assert len(search_attempts) == 2
    assert all(item["ok"] is False for item in search_attempts)
    assert search_failed.result.status == "tool_failure"
    assert "素材检索" in search_failed.result.message
    assert search_failed.result.source_ids == []

    estimate_failed = _run("tool-failure-estimate", _full(), failures={"estimate": 2})
    assert estimate_failed.result.status == "tool_failure"
    assert "时长估算" in estimate_failed.result.message
    assert estimate_failed.result.source_ids == ["P01"]
    assert estimate_failed.result.shots

    check_failed = _run("tool-failure-check", _full(), failures={"check_rules": 2})
    assert check_failed.result.status == "tool_failure"
    assert "规则检查" in check_failed.result.message
    assert check_failed.result.estimated_duration_sec == 2.0
    assert check_failed.result.source_ids == ["P01"]


def test_over_duration_is_cut_from_38_seconds_to_28():
    output = _run("over-duration-revised", _full(theme="详细介绍支持字幕"))
    estimates = [
        item["observation"]["total_ms"]
        for item in output.trace
        if item["action"] == "estimate" and item["ok"]
    ]
    drafts = [item["arguments"]["shots"][0]["narration"] for item in output.trace if item["action"] == "draft"]
    assert spoken_count(drafts[0]) == 152
    assert spoken_count(drafts[1]) == 112
    assert estimates == [38000, 28000]
    assert output.result.status == "completed"
    assert output.result.estimated_duration_sec == 28.0
    assert output.result.shots[0].duration_sec == 28.0
    assert output.result.source_ids == ["P01"]
    assert "支持字幕" in output.result.shots[0].narration
    assert "%" not in output.result.shots[0].narration
    assert "短于目标时长" in output.result.risks


def test_required_line_longer_than_target_is_unsatisfied():
    output = _run(
        "over-duration-unsatisfied",
        _full(duration_sec=4),
        rules="rules-disclaimer.jsonl",
    )
    assert output.result.status == "unsatisfied"
    assert "BR-DISCLAIMER" in output.result.message
    assert "5.250" in output.result.message
    assert output.result.estimated_duration_sec == 6.25
    assert DISCLAIMER in output.result.shots[0].narration
    assert output.result.source_ids == ["P01"]
    assert output.result.status != "completed"


def test_invented_percent_is_removed_before_completion():
    output = _run("number-claim", _full(theme="介绍支持字幕的效果"))
    checks = [item for item in output.trace if item["action"] == "check_rules" and item["ok"]]
    assert checks[0]["observation"]["passed"] is False
    assert any(item["rule_id"] == "FACT-NUMBER" for item in checks[0]["observation"]["violations"])
    assert checks[-1]["observation"]["passed"] is True
    assert output.result.status == "completed"
    assert "80%" not in output.result.shots[0].narration
    assert "80%" not in output.result.title
    assert "支持字幕" in output.result.shots[0].narration
