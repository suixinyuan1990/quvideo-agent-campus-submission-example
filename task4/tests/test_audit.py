"""Audit: source ids, shot durations, and checks must line up.

Changing the target duration or the retrieved body must change the next action.
A completed script that states a product fact absent from the cited body is a critical defect.
"""

import json
from pathlib import Path

from script_agent.corpus import Corpus
from script_agent.loop import run
from script_agent.rules import load_rules
from script_agent.schema import Attribute, Request
from script_agent.textutil import number_tokens, target_ms

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "fixtures"
REPORT = ROOT / "examples" / "audit" / "report.json"


def request(theme: str, duration: float) -> Request:
    return Request(
        theme=theme,
        duration_sec=duration,
        audience="功能介绍观众",
        platform="抖音",
        style="口播",
    )


def actions(output) -> list[str]:
    return [item["action"] for item in output.trace]


def next_action(output, name: str) -> str | None:
    for index, item in enumerate(output.trace):
        if item["action"] == name and item.get("ok", True):
            if index + 1 < len(output.trace):
                return output.trace[index + 1]["action"]
            return None
    return None


def last_observation(output, name: str) -> dict | None:
    found = [item["observation"] for item in output.trace if item["action"] == name and item.get("ok")]
    return found[-1] if found else None


def retrieved_ids(output) -> list[str]:
    found: list[str] = []
    for item in output.trace:
        if item["action"] != "search" or not item.get("ok"):
            continue
        for hit in item["observation"]:
            if hit["source_id"] not in found:
                found.append(hit["source_id"])
    return found


def replace_p01(corpus: Corpus, body: str, key: str, value: str) -> Corpus:
    original = corpus.by_id["P01"]
    updated = original.model_copy(
        update={"body": body, "attributes": [Attribute(key=key, value=value)]}
    )
    return Corpus([updated])


def alignment_problems(output, corpus: Corpus, duration: float) -> list[str]:
    result = output.result
    problems: list[str] = []
    ids = retrieved_ids(output)
    shot_ids: list[str] = []
    for shot in result.shots:
        for source_id in shot.source_ids:
            if source_id not in shot_ids:
                shot_ids.append(source_id)
            if source_id not in ids:
                problems.append(f"镜头 {shot.index} 的来源 {source_id} 不在检索结果里")
            elif source_id not in corpus.by_id:
                problems.append(f"来源 {source_id} 不在语料里")
    if result.source_ids != shot_ids:
        problems.append("汇总来源 ID 与分镜来源 ID 不一致")
    estimate = last_observation(output, "estimate")
    if result.shots or result.estimated_duration_sec is not None:
        if estimate is None:
            problems.append("交付了时长，但 Trace 里没有成功的估算")
        else:
            if result.estimated_duration_sec != estimate["total_sec"]:
                problems.append("总时长与最后一次估算不一致")
            timings = {item["index"]: item for item in estimate["shots"]}
            for shot in result.shots:
                timing = timings.get(shot.index)
                if timing is None or shot.duration_sec != timing["duration_sec"]:
                    problems.append(f"镜头 {shot.index} 的时长与估算不一致")
    check = last_observation(output, "check_rules")
    if result.status == "completed":
        if check is None or not check["passed"]:
            problems.append("状态是 completed，最近一次规则检查没有通过")
        if estimate is None or estimate["total_ms"] > target_ms(duration):
            problems.append("状态是 completed，最近一次估算超过目标时长")
    return problems


def fabricated_facts(output, corpus: Corpus) -> list[str]:
    if output.result.status != "completed":
        return []
    found: list[str] = []
    for shot in output.result.shots:
        bodies = [corpus.by_id[source_id].body for source_id in shot.source_ids if source_id in corpus.by_id]
        cited = "\n".join(bodies)
        text = "\n".join([output.result.title, shot.narration, shot.subtitle])
        for token in number_tokens(text):
            if token not in cited:
                found.append(token)
        if output.result.title and output.result.title not in cited:
            found.append(output.result.title)
        if "效率提升" in text and "效率提升" not in cited:
            found.append("效率提升")
    return found


def test_audit_traceability_and_adjustment():
    corpus = Corpus.load(FIXTURES / "materials.jsonl")
    rules = load_rules(FIXTURES / "rules-disclaimer.jsonl")
    detailed_30 = run(request("详细介绍支持字幕", 30), corpus)
    detailed_40 = run(request("详细介绍支持字幕", 40), corpus)
    detailed_20 = run(request("详细介绍支持字幕", 20), corpus)
    detailed_1 = run(request("详细介绍支持字幕", 1), corpus)
    normal = run(request("介绍支持字幕", 30), corpus)
    numbers = run(request("介绍支持字幕的效果", 30), corpus)
    blocked = run(request("介绍支持字幕", 4), corpus, rules)
    empty = run(request("运动鞋气垫", 30), corpus)
    wiped = run(request("介绍支持字幕", 30), replace_p01(corpus, "食堂菜单。工作日午餐供应两荤一素。", "内容", "食堂菜单"))
    renamed_corpus = replace_p01(corpus, "功能#字幕翻译", "功能", "字幕翻译")
    renamed = run(request("介绍字幕翻译", 30), renamed_corpus)

    checked = {
        "detailed_30": (detailed_30, corpus, 30),
        "detailed_40": (detailed_40, corpus, 40),
        "detailed_20": (detailed_20, corpus, 20),
        "detailed_1": (detailed_1, corpus, 1),
        "normal": (normal, corpus, 30),
        "numbers": (numbers, corpus, 30),
        "blocked": (blocked, corpus, 4),
        "empty": (empty, corpus, 30),
        "wiped": (wiped, corpus, 30),
        "renamed": (renamed, renamed_corpus, 30),
    }
    alignment = {name: alignment_problems(output, used, duration) for name, (output, used, duration) in checked.items()}
    fabrication = {
        "detailed_30": fabricated_facts(detailed_30, corpus),
        "detailed_40": fabricated_facts(detailed_40, corpus),
        "normal": fabricated_facts(normal, corpus),
        "numbers": fabricated_facts(numbers, corpus),
        "renamed": fabricated_facts(renamed, renamed_corpus),
    }
    critical = []
    for name, facts in fabrication.items():
        if facts:
            critical.append(f"{name} 的完成稿包含素材正文里没有的产品事实：{'、'.join(facts)}")
    if any(alignment.values()):
        critical.append("来源 ID、分镜时长或检查结果没有逐一对应")

    first_number_check = next(item["observation"] for item in numbers.trace if item["action"] == "check_rules" and item.get("ok"))
    number_fixed = (
        numbers.result.status == "completed"
        and not first_number_check["passed"]
        and any(item["rule_id"] == "FACT-NUMBER" for item in first_number_check["violations"])
        and "80%" not in numbers.result.shots[0].narration
        and "效率提升" not in numbers.result.shots[0].narration
    )
    duration_40_adjusted = (
        next_action(detailed_30, "check_rules") == "draft"
        and next_action(detailed_40, "check_rules") == "finish"
        and detailed_40.result.status == "completed"
        and detailed_40.result.estimated_duration_sec == 38.0
        and actions(detailed_30) != actions(detailed_40)
    )
    duration_20_adjusted = (
        detailed_20.result.status == "completed"
        and detailed_20.result.estimated_duration_sec == 2.0
        and detailed_20.result.shots[0].narration == "这个功能支持字幕"
        and detailed_20.result.source_ids == ["P01"]
        and actions(detailed_20) != actions(detailed_30)
        and next_action(detailed_20, "check_rules") == "draft"
        and detailed_1.result.status == "unsatisfied"
        and detailed_1.result.estimated_duration_sec == 2.0
        and detailed_1.result.shots[0].narration == "这个功能支持字幕"
    )
    search_wiped_adjusted = (
        next_action(normal, "search") == "draft"
        and next_action(wiped, "search") == "search"
        and wiped.result.status == "no_material"
        and wiped.result.source_ids == []
        and actions(normal) != actions(wiped)
    )
    search_renamed_adjusted = (
        renamed.result.status == "completed"
        and renamed.result.title == "字幕翻译"
        and "字幕翻译" in renamed.result.shots[0].narration
        and "支持字幕" not in renamed.result.title
        and "支持字幕" not in renamed.result.shots[0].narration
        and renamed.result.title in renamed_corpus.by_id["P01"].body
    )

    traceable = 0
    if not any(alignment.values()):
        traceable += 30
    if critical == [] and all(item == [] for item in fabrication.values()):
        traceable += 20
    correction = 0
    if duration_40_adjusted:
        correction += 10
    if duration_20_adjusted:
        correction += 10
    if search_wiped_adjusted:
        correction += 15
    if search_renamed_adjusted:
        correction += 10
    if number_fixed:
        correction += 5
    if critical:
        traceable = 0

    report = {
        "score": {"traceable": traceable, "correction": correction, "total": traceable + correction},
        "critical_defects": critical,
        "alignment": alignment,
        "fabrication": fabrication,
        "duration_change": {
            "at_30": {
                "status": detailed_30.result.status,
                "actions": actions(detailed_30),
                "next_after_first_check": next_action(detailed_30, "check_rules"),
                "estimated_duration_sec": detailed_30.result.estimated_duration_sec,
                "source_ids": detailed_30.result.source_ids,
                "shot_duration_sec": [shot.duration_sec for shot in detailed_30.result.shots],
            },
            "at_40": {
                "status": detailed_40.result.status,
                "actions": actions(detailed_40),
                "next_after_first_check": next_action(detailed_40, "check_rules"),
                "estimated_duration_sec": detailed_40.result.estimated_duration_sec,
                "source_ids": detailed_40.result.source_ids,
            },
            "at_20": {
                "status": detailed_20.result.status,
                "actions": actions(detailed_20),
                "next_after_first_check": next_action(detailed_20, "check_rules"),
                "estimated_duration_sec": detailed_20.result.estimated_duration_sec,
                "source_ids": detailed_20.result.source_ids,
                "shot_duration_sec": [shot.duration_sec for shot in detailed_20.result.shots],
                "narration": detailed_20.result.shots[0].narration,
            },
            "at_1": {
                "status": detailed_1.result.status,
                "actions": actions(detailed_1),
                "estimated_duration_sec": detailed_1.result.estimated_duration_sec,
                "source_ids": detailed_1.result.source_ids,
                "narration": detailed_1.result.shots[0].narration,
            },
        },
        "search_change": {
            "original_next_after_search": next_action(normal, "search"),
            "original_actions": actions(normal),
            "original_title": normal.result.title,
            "wiped_next_after_search": next_action(wiped, "search"),
            "wiped_actions": actions(wiped),
            "wiped_status": wiped.result.status,
            "renamed_title": renamed.result.title,
            "renamed_narration": renamed.result.shots[0].narration,
            "renamed_actions": actions(renamed),
            "renamed_source_ids": renamed.result.source_ids,
        },
        "number_correction": {
            "first_check_passed": first_number_check["passed"],
            "first_violation_ids": [item["rule_id"] for item in first_number_check["violations"]],
            "final_status": numbers.result.status,
            "final_narration": numbers.result.shots[0].narration,
            "final_source_ids": numbers.result.source_ids,
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    assert alignment == {name: [] for name in alignment}
    assert fabrication == {name: [] for name in fabrication}
    assert duration_40_adjusted
    assert duration_20_adjusted
    assert search_wiped_adjusted
    assert search_renamed_adjusted
    assert number_fixed
    assert critical == []
    assert report["score"]["total"] == 100
