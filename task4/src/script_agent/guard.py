"""Checks that a completed script matches the tool results."""

from script_agent.schema import Draft, Estimate, Hit, CheckResult
from script_agent.textutil import target_ms


def completion_problems(
    draft: Draft,
    estimate: Estimate | None,
    check: CheckResult | None,
    hits: list[Hit],
    duration_sec: float,
    style: str,
) -> list[str]:
    problems: list[str] = []
    if not draft.title.strip():
        problems.append("标题为空")
    if not draft.shots:
        problems.append("分镜为空")
    retrieved = {hit.source_id: hit for hit in hits}
    for shot in draft.shots:
        if not shot.visual.strip():
            problems.append(f"镜头 {shot.index} 缺少画面")
        for source_id in shot.source_ids:
            hit = retrieved.get(source_id)
            if hit is None:
                problems.append(f"来源 {source_id} 不在本轮检索结果里")
                continue
            if not _cites_value(hit, draft.title, shot.narration, shot.subtitle):
                problems.append(f"镜头 {shot.index} 没有写出来源 {source_id} 的属性值")
    if style == "纯字幕":
        if not any(shot.subtitle.strip() for shot in draft.shots):
            problems.append("纯字幕稿至少有一镜字幕")
    elif not any(shot.narration.strip() for shot in draft.shots):
        problems.append("口播稿至少有一镜旁白")
    if estimate is None:
        problems.append("还没有时长估算")
    elif estimate.total_ms > target_ms(duration_sec):
        problems.append(
            f"预计总时长 {estimate.total_sec:.3f} 秒超过目标 {duration_sec:g} 秒"
        )
    if check is None:
        problems.append("还没有规则检查")
    elif not check.passed:
        blocked = [item.rule_id for item in check.violations if item.blocking]
        problems.append("阻断规则未通过：" + "、".join(blocked))
    return problems


def _cites_value(hit: Hit, title: str, narration: str, subtitle: str) -> bool:
    text = "\n".join([title, narration, subtitle])
    long_values = [attribute.value for attribute in hit.attributes if len(attribute.value) >= 2]
    if long_values:
        return any(value in text for value in long_values)
    return any(attribute.value and attribute.value in text for attribute in hit.attributes)
