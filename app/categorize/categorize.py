"""The categorize stage: config-driven category assignment (gatherer-neutral).

`apply()` is called from `app.ingest.process_source()` between the gatherer and
the sieve. It mutates `ScrapedEvent.categories` in place BEFORE the sieve hashes,
so category assignment participates in change detection. Rules are declared in
`intake.yaml` (`sources[].rules`, plus the implicit `default_categories` assign
rule) — a single implementation for all category assignment (F50.04).

Every assigned/gathered name is then slugified + qualified to a `class:name`
identity before the sieve sees it, so the DB only ever stores clean category
slugs.
"""
# Contract: Categorize v5 (docs/CATEGORIZE_CONTRACT.md)
CONTRACT_VERSION = 5

#region: imports
import re

from app.intake import load as load_intake
from app.schema import CategoryRule, ScrapedEvent, SourceConfig
from app.services.categories import qualify, slugify
#endregion


#region: fields
TEXT_FIELDS = ("uid", "title", "description", "location", "url")
#endregion


#region: rules
def _default_rules(source: SourceConfig) -> list[CategoryRule]:
    if not source.default_categories:
        return []
    return [CategoryRule(mode="assign", categories=source.default_categories)]


def _global_rules() -> list[CategoryRule]:
    return list(load_intake().rules)


def _gatherer_rules(source: SourceConfig) -> list[CategoryRule]:
    gatherer = load_intake().gatherers.get(source.gatherer)
    if gatherer is None:
        return []
    return list(gatherer.rules)


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


#region: resolve
def resolve_rules(source: SourceConfig) -> list[CategoryRule]:
    """Return the configured rules for `source` (global → gatherer → defaults → source)."""
    return _global_rules() + _gatherer_rules(source) + _default_rules(source) + source.rules
#endregion


#region: apply
def apply(source: SourceConfig, events: list[ScrapedEvent], rules: list[CategoryRule] | None = None) -> None:
    """Apply category rules in place.

    `rules=None` resolves the configured rules (global + gatherer + defaults +
    source); otherwise the given list is applied (used by the debug playground to
    test custom rules). After all rules run, every name is slugified and
    qualified to `class:name` (empty slugs dropped).
    """
    if rules is None:
        rules = resolve_rules(source)
    for rule in rules:
        _apply_rule(rule, events)

    for event in events:
        event.categories = sorted({qualify(name) for name in event.categories if slugify(name)})
#endregion
