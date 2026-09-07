"""The categorize stage: config-driven category assignment (gatherer-neutral).

`apply()` is called from `app.ingest.process_source()` between the gatherer and
the sieve. It mutates `ScrapedEvent.categories` in place BEFORE the sieve hashes,
so category assignment participates in change detection. Rules are declared in
`intake.yaml` (`sources[].rules`, plus the implicit `default_categories` assign
rule) — a single implementation for all category assignment (F50.04).
"""
# Contract: Categorize v1 (docs/CATEGORIZE_CONTRACT.md)
CONTRACT_VERSION = 1

#region: imports
import re

from app.schema import CategoryRule, ScrapedEvent, SourceConfig
#endregion


#region: fields
TEXT_FIELDS = ("uid", "title", "description", "location", "url")
#endregion


#region: rules
def _default_rules(source: SourceConfig) -> list[CategoryRule]:
    if not source.default_categories:
        return []
    return [CategoryRule(mode="assign", categories=source.default_categories)]


def _selected_fields(rule: CategoryRule) -> list[str]:
    if not rule.fields or "*" in rule.fields:
        return list(TEXT_FIELDS)
    return rule.fields


def _apply_rule(rule: CategoryRule, events: list[ScrapedEvent]) -> None:
    if not rule.categories:
        return

    if rule.mode == "assign":
        for event in events:
            event.categories = sorted(set(event.categories) | set(rule.categories))
        return

    if rule.mode == "regex":
        if not rule.regex:
            return
        pattern = re.compile(rule.regex)
        fields = _selected_fields(rule)
        for event in events:
            if any(pattern.search(getattr(event, field) or "") for field in fields):
                event.categories = sorted(set(event.categories) | set(rule.categories))
#endregion


#region: apply
def apply(source: SourceConfig, events: list[ScrapedEvent]) -> None:
    """Apply the source's category rules (defaults + explicit) in place."""
    for rule in _default_rules(source) + source.rules:
        _apply_rule(rule, events)
#endregion
