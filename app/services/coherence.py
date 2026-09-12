"""Config/intake coherence checks.

`check()` is called from the `/debug` dashboard. It returns a list of issues
(`severity`, `scope`, `message`) so an incoherent config is visible instead of
failing silently. Every check is defensive — it converts its own errors into an
issue rather than raising, so a broken config can never crash the page.
"""
#region: imports
import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.config import settings
from app.intake import IntakeSettings
from app.services.categories import slugify
#endregion


#region: helpers
def _issue(severity: str, scope: str, message: str) -> dict:
    return {"severity": severity, "scope": scope, "message": message}
#endregion


#region: check
def check() -> list[dict]:
    """Run all coherence checks; return a list of issue dicts (empty = all good)."""
    issues: list[dict] = []
    issues.extend(_check_intake())
    issues.extend(_check_config())
    return issues
#endregion


#region: intake
def _check_intake() -> list[dict]:
    issues: list[dict] = []
    path = Path(settings.intake_file)
    if not path.exists():
        return issues  # missing intake is fine (empty defaults)

    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        issues.append(_issue("error", "intake", f"{settings.intake_file} is not valid YAML: {exc}"))
        return issues

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        issues.append(_issue("error", "intake", f"{settings.intake_file} must be a mapping, got {type(raw).__name__}"))
        return issues

    try:
        intake = IntakeSettings(**raw)
    except ValidationError as exc:
        issues.append(_issue("error", "intake", f"{settings.intake_file} validation failed: {exc}"))
        return issues
    except TypeError as exc:
        issues.append(_issue("error", "intake", f"{settings.intake_file} is malformed: {exc}"))
        return issues

    issues.extend(_check_gatherers(intake))
    issues.extend(_check_categories(intake))
    issues.extend(_check_rules(intake))
    return issues


def _check_rules(intake: IntakeSettings) -> list[dict]:
    import re

    from app.categorize.categorize import TEXT_FIELDS

    issues: list[dict] = []

    def check_rule_list(prefix: str, rules) -> None:
        for rule in rules:
            p = f"{prefix}: rule {rule.mode!r}"
            if rule.mode == "regex":
                if not rule.regex:
                    issues.append(_issue("error", "intake", f"{p} is missing a regex"))
                    continue
                try:
                    re.compile(rule.regex)
                except re.error as exc:
                    issues.append(_issue("error", "intake", f"{p} has an invalid regex ({exc})"))
                for field in rule.fields:
                    if field not in TEXT_FIELDS and field != "*":
                        issues.append(_issue("warning", "intake", f"{p} references unknown field {field!r}"))
            elif rule.mode != "assign":
                issues.append(_issue("error", "intake", f"{p} is not a known mode"))

    check_rule_list("global", intake.rules)
    for name, gatherer in intake.gatherers.items():
        check_rule_list(f"gatherer {name!r}", gatherer.rules)
    for cfg in intake.sources:
        check_rule_list(f"source {cfg.name!r}", cfg.rules)
    return issues


def _check_gatherers(intake: IntakeSettings) -> list[dict]:
    from app.registry import load_gatherer

    issues: list[dict] = []
    for cfg in intake.sources:
        try:
            load_gatherer(cfg.gatherer)
        except Exception as exc:
            issues.append(
                _issue("error", "intake", f"source {cfg.name!r}: gatherer {cfg.gatherer!r} failed to load ({exc})")
            )
    return issues


def _check_categories(intake: IntakeSettings) -> list[dict]:
    issues: list[dict] = []

    membership: dict[str, list[str]] = {}
    for class_name, names in intake.category_definitions.items():
        for name in names:
            membership.setdefault(slugify(name), []).append(class_name)
    for name, classes in membership.items():
        if len(classes) > 1:
            issues.append(_issue("error", "intake", f"category {name!r} is listed under multiple classes: {classes}"))

    for class_name in intake.category_definitions:
        if slugify(class_name) != class_name:
            issues.append(_issue("warning", "intake", f"class {class_name!r} is not a valid slug (becomes {slugify(class_name)!r})"))

    exposed = {slugify(c) for c in intake.exposed_classes}
    defined = {slugify(c) for c in intake.category_definitions}
    if defined:
        for class_name in sorted(exposed - defined):
            issues.append(
                _issue("warning", "intake", f"exposed class {class_name!r} is not defined in category_definitions")
            )

    for internal, external in intake.category_symlinks.items():
        if internal == external:
            issues.append(_issue("warning", "intake", f"category symlink {internal!r} maps to itself"))
        elif external.split(":", 1)[0] not in exposed:
            issues.append(
                _issue("warning", "intake", f"category symlink {internal!r} resolves to a non-exposed class {external!r}")
            )

    return issues
#endregion


#region: config
def _check_config() -> list[dict]:
    issues: list[dict] = []
    data_dir = Path(settings.data_dir)
    if data_dir.exists() and not os.access(data_dir, os.W_OK):
        issues.append(_issue("error", "config", f"data_dir {str(data_dir)!r} is not writable"))
    return issues
#endregion
