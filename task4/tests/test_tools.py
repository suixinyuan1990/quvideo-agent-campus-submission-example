import json
from pathlib import Path

import pytest

from script_agent.corpus import Corpus
from script_agent.schema import Draft, Hit, Material, ShotDraft
from script_agent.textutil import duration_ms, spoken_count
from script_agent.tools import FailurePlan, check_draft

ROOT = Path(__file__).resolve().parents[1]
DISCLAIMER = "本视频仅介绍已列出的功能，具体以产品说明为准。"


def test_spoken_duration_matches_reference_lengths():
    assert spoken_count(DISCLAIMER) == 21
    assert duration_ms(21, 4) == 5250
    assert duration_ms(152, 4) == 38000
    assert duration_ms(112, 4) == 28000
    assert spoken_count("支持字幕。") == 4


def test_search_hits_subtitle_fact_and_skips_unrelated_query():
    corpus = Corpus.load(ROOT / "data" / "fixtures" / "materials.jsonl")
    subtitle = corpus.search("字幕")
    assert [hit.source_id for hit in subtitle] == ["P01"]
    assert corpus.search("运动鞋气垫") == []


def test_search_ranks_the_matching_attribute_first():
    corpus = Corpus(
        [
            Material(source_id="P01", body="功能#支持字幕", attributes=[{"key": "功能", "value": "支持字幕"}]),
            Material(source_id="P02", body="功能#气垫", attributes=[{"key": "功能", "value": "气垫"}]),
        ]
    )
    hits = corpus.search("气垫")
    assert hits[0].source_id == "P02"


def test_reference_summary_is_not_indexed():
    with pytest.raises(ValueError, match="可引用正文"):
        Corpus.load(ROOT / "data" / "advertisegen" / "reference_summaries.jsonl")


def test_duplicate_subtitle_reports_each_missing_number_once():
    hit = Hit(source_id="P01", body="功能#支持字幕", attributes=[{"key": "功能", "value": "支持字幕"}], matched_values=[], score=1)
    narration = "支持字幕，效率提升 80%"
    draft = Draft(
        title="支持字幕",
        shots=[ShotDraft(index=1, visual="产品界面", narration=narration, subtitle=narration, source_ids=["P01"])],
    )
    checked = check_draft(draft, [], [hit], FailurePlan())
    numbers = [item for item in checked.violations if item.rule_id == "FACT-NUMBER"]
    assert len(numbers) == 1
    assert "80%" in numbers[0].message


def test_advertisegen_percent_is_not_a_citable_fact():
    material = None
    with (ROOT / "data" / "advertisegen" / "documents.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if '"AG-dev-000533"' in line:
                material = json.loads(line)
                break
    assert material is not None
    assert material["body"] == "类型#上衣*材质#棉*风格#简约*衣样式#衬衫*衣领型#翻领*衣款式#拼接"
    assert "100%" not in material["body"]
    corpus = Corpus([Material.model_validate(material)])
    hit = corpus.search("棉衬衫")[0]
    draft = Draft(
        title="棉衬衫",
        shots=[
            ShotDraft(
                index=1,
                visual="衣服",
                narration="面料选用100%高支棉",
                source_ids=[hit.source_id],
            )
        ],
    )
    checked = check_draft(draft, [], [hit], FailurePlan())
    assert any(item.rule_id == "FACT-NUMBER" and "100%" in item.message for item in checked.violations)
