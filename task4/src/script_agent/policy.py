"""Fixed actions for acceptance. The real model is not used here."""

from script_agent.schema import (
    CheckAction,
    DraftAction,
    EstimateAction,
    FinishAction,
    Rule,
    SearchAction,
    ShotDraft,
)
from script_agent.textutil import chars_per_second, duration_ms, pad_to_spoken_length, seconds_of, spoken_count, target_ms


def decide(state) -> SearchAction | DraftAction | EstimateAction | CheckAction | FinishAction:
    if state.guard_error:
        return _recover(state)
    if not state.hits:
        return _search_or_stop(state)
    if state.draft is None:
        return _opening_draft(state)
    if state.estimate is None:
        return EstimateAction(action="estimate")
    if state.check is None:
        return CheckAction(action="check_rules")
    return _after_checks(state)


def _search_or_stop(state):
    theme = (state.request.theme or "").strip()
    if state.search_count == 0:
        return SearchAction(action="search", query=theme)
    if state.search_count == 1:
        previous = state.queries[-1] if state.queries else theme
        rewritten = _rewrite(theme, previous)
        if rewritten != previous:
            return SearchAction(action="search", query=rewritten)
    return FinishAction(action="finish", status="no_material", message="改写查询后仍然没有命中素材。")


def _opening_draft(state):
    fact = _fact(state)
    rule = _exceeding_rule(state)
    theme = state.request.theme or ""
    if rule is not None:
        return _draft(state, f"{fact}。{rule.phrase}")
    if "效果" in theme:
        return _draft(state, f"{fact}，效率提升 80%")
    if "详细" in theme:
        return _draft(state, pad_to_spoken_length(152, fact))
    return _draft(state, f"这个功能{fact}")


def _after_checks(state):
    if _has_blocking(state, "FACT-NUMBER") and state.revisions < 2:
        return _draft(state, f"这个功能{_fact(state)}")
    rule = _exceeding_rule(state)
    over = state.estimate.total_ms > target_ms(state.request.duration_sec)
    if rule is not None and over:
        return FinishAction(action="finish", status="unsatisfied", message=_unsatisfied_message(state, rule))
    if over and state.revisions < 2:
        shorter = _shorter_narration(state)
        if shorter is not None:
            return _draft(state, shorter)
    if over:
        return FinishAction(
            action="finish",
            status="unsatisfied",
            message=f"调整后预计总时长仍为 {state.estimate.total_sec:.3f} 秒，超过目标 {state.request.duration_sec:g} 秒。",
        )
    if not state.check.passed:
        blocked = "、".join(item.rule_id for item in state.check.violations if item.blocking)
        return FinishAction(action="finish", status="unsatisfied", message=f"阻断规则未通过：{blocked}")
    return FinishAction(action="finish", status="completed", message="")


def _recover(state):
    if state.revisions < 2 and "FACT-NUMBER" in (state.guard_error or ""):
        return _draft(state, f"这个功能{_fact(state)}")
    if state.revisions < 2 and "超过" in (state.guard_error or ""):
        return _draft(state, pad_to_spoken_length(112, _fact(state)))
    return FinishAction(action="finish", status="unsatisfied", message=state.guard_error or "结果没有通过校验。")


def _draft(state, narration: str) -> DraftAction:
    fact = _fact(state)
    if fact not in narration:
        narration = fact + narration
    return DraftAction(
        action="draft",
        title=fact,
        shots=[
            ShotDraft(
                index=1,
                visual="产品界面",
                narration=narration,
                subtitle=narration,
                source_ids=[state.hits[0].source_id],
            )
        ],
    )


def _shorter_narration(state) -> str | None:
    fact = _fact(state)
    current = state.draft.shots[0].narration if state.draft and state.draft.shots else ""
    current_count = spoken_count(current)
    if current_count > 112 and spoken_count(fact) <= 112:
        return pad_to_spoken_length(112, fact)
    minimal = f"这个功能{fact}"
    if spoken_count(minimal) < current_count:
        return minimal
    return None


def _fact(state) -> str:
    hit = state.hits[0]
    values = [item.value for item in hit.attributes if len(item.value) >= 2]
    if values:
        return max(values, key=len)
    if hit.attributes and hit.attributes[0].value:
        return hit.attributes[0].value
    return hit.body


def _exceeding_rule(state):
    rate = chars_per_second(state.request.effective_style)
    limit = target_ms(state.request.duration_sec)
    for rule in state.rules:
        if rule.kind != "require_substring" or not rule.blocking or not rule.phrase:
            continue
        if duration_ms(spoken_count(rule.phrase), rate) > limit:
            return rule
    return None


def _has_blocking(state, rule_id: str) -> bool:
    return any(item.blocking and item.rule_id == rule_id for item in state.check.violations)


def _unsatisfied_message(state, rule: Rule) -> str:
    rate = chars_per_second(state.request.effective_style)
    phrase_ms = duration_ms(spoken_count(rule.phrase or ""), rate)
    return (
        f"规则 {rule.rule_id} 要求保留固定声明，该声明估算为 {seconds_of(phrase_ms):.3f} 秒，"
        f"目标时长为 {state.request.duration_sec:g} 秒，两者不能同时满足。"
        f"最后一次估算为 {state.estimate.total_sec:.3f} 秒。"
    )


def _rewrite(theme: str, previous: str) -> str:
    if "运动鞋" in theme:
        return "运动鞋"
    stripped = theme
    for word in ("详细", "介绍", "功能", "效果", "的"):
        stripped = stripped.replace(word, "")
    stripped = stripped.strip()
    if stripped and stripped != previous:
        return stripped
    if len(previous) > 2:
        return previous[:-2]
    return previous
