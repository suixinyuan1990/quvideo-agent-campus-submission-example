"""Brand-rule file. Numeric claims are checked separately and always apply."""

import json
import re
from pathlib import Path

from script_agent.schema import Rule


def load_rules(path: Path | str | None) -> list[Rule]:
    if path is None:
        return []
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    rules: list[Rule] = []
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rule = Rule.model_validate(json.loads(line))
            if rule.kind == "forbid_regex":
                if not rule.pattern:
                    raise ValueError(f"{rule.rule_id} 缺少 pattern")
                re.compile(rule.pattern)
            elif rule.kind == "require_substring" and not rule.phrase:
                raise ValueError(f"{rule.rule_id} 缺少 phrase")
            rules.append(rule)
    return rules
