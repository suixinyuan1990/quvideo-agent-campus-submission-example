"""Search, duration, and rule check. Tools do not rewrite the draft."""

import re

from script_agent.corpus import Corpus
from script_agent.schema import CheckResult, Draft, Estimate, Hit, Rule, ShotTiming, Violation
from script_agent.textutil import chars_per_second, duration_ms, number_tokens, seconds_of, spoken_count


class ToolFailure(Exception):
    def __init__(self, tool: str) -> None:
        super().__init__(tool)
        self.tool = tool


class FailurePlan:
    """Test hook. Each name fails once per remaining count, then succeeds."""

    def __init__(self, counts: dict[str, int] | None = None) -> None:
        self.counts = dict(counts or {})

    def check(self, tool: str) -> None:
        left = self.counts.get(tool, 0)
        if left > 0:
            self.counts[tool] = left - 1
            raise ToolFailure(tool)


def search_materials(corpus: Corpus, query: str, failures: FailurePlan) -> list[Hit]:
    failures.check("search")
    return corpus.search(query)


def estimate_draft(draft: Draft, style: str, failures: FailurePlan) -> Estimate:
    failures.check("estimate")
    rate = chars_per_second(style)
    timings: list[ShotTiming] = []
    total = 0
    for shot in draft.shots:
        text = _carrier_text(shot.narration, shot.subtitle, style)
        count = spoken_count(text)
        milliseconds = duration_ms(count, rate)
        total += milliseconds
        timings.append(
            ShotTiming(
                index=shot.index,
                duration_ms=milliseconds,
                duration_sec=seconds_of(milliseconds),
                spoken_chars=count,
            )
        )
    return Estimate(
        total_ms=total,
        total_sec=seconds_of(total),
        shots=timings,
        chars_per_second=rate,
    )


def check_draft(
    draft: Draft,
    rules: list[Rule],
    hits: list[Hit],
    failures: FailurePlan,
) -> CheckResult:
    failures.check("check_rules")
    violations: list[Violation] = []
    fields = _fields(draft)
    for rule in rules:
        violations.extend(_apply_rule(rule, fields))
    violations.extend(_number_violations(draft, hits))
    blocking = any(item.blocking for item in violations)
    return CheckResult(passed=not blocking, violations=violations)


def _carrier_text(narration: str, subtitle: str, style: str) -> str:
    if style == "纯字幕":
        return subtitle or narration
    return narration or subtitle


def _fields(draft: Draft) -> list[tuple[str, str]]:
    fields = [("title", draft.title)]
    seen = {draft.title}
    for shot in draft.shots:
        for location, text in (
            (f"shot:{shot.index}", shot.narration),
            (f"shot:{shot.index}:subtitle", shot.subtitle),
        ):
            if not text or text in seen:
                continue
            seen.add(text)
            fields.append((location, text))
    return fields


def _apply_rule(rule: Rule, fields: list[tuple[str, str]]) -> list[Violation]:
    if rule.kind == "forbid_regex":
        pattern = re.compile(rule.pattern or "")
        found: list[Violation] = []
        for location, text in fields:
            if pattern.search(text):
                found.append(
                    Violation(
                        rule_id=rule.rule_id,
                        location=location,
                        message=rule.note or f"命中禁用规则 {rule.rule_id}",
                        blocking=rule.blocking,
                    )
                )
        return found
    phrase = rule.phrase or ""
    combined = "\n".join(text for _, text in fields)
    if phrase in combined:
        return []
    return [
        Violation(
            rule_id=rule.rule_id,
            location="script",
            message=rule.note or f"缺少必须出现的原文：{phrase}",
            blocking=rule.blocking,
        )
    ]


def _number_violations(draft: Draft, hits: list[Hit]) -> list[Violation]:
    by_id = {hit.source_id: hit.body for hit in hits}
    violations: list[Violation] = []
    title_tokens = [token for token in number_tokens(draft.title) if not _token_in_cited(token, draft, by_id)]
    for token in title_tokens:
        violations.append(_number_violation(token, "title"))
    for shot in draft.shots:
        cited = "\n".join(by_id.get(source_id, "") for source_id in shot.source_ids)
        texts = [shot.narration]
        if shot.subtitle and shot.subtitle != shot.narration:
            texts.append(shot.subtitle)
        seen: set[str] = set()
        for text in texts:
            for token in number_tokens(text):
                if token in seen or token in cited:
                    continue
                seen.add(token)
                violations.append(_number_violation(token, f"shot:{shot.index}"))
    return violations


def _token_in_cited(token: str, draft: Draft, by_id: dict[str, str]) -> bool:
    cited_ids = [source_id for shot in draft.shots for source_id in shot.source_ids]
    return any(token in by_id.get(source_id, "") for source_id in cited_ids)


def _number_violation(token: str, location: str) -> Violation:
    return Violation(
        rule_id="FACT-NUMBER",
        location=location,
        message=f"数字「{token}」没有出现在已引用素材的正文里",
        blocking=True,
    )
