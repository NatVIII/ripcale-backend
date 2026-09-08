"""Tests for the categorize stage (F50)."""
#region: imports
from datetime import datetime

from app.categorize import apply
from app.schema import CategoryRule, GathererConfig, ScrapedEvent, SourceConfig
#endregion


def _cfg(**kwargs):
    return SourceConfig(name="Test", gatherer="elfsight", url="https://x", **kwargs)


def _set_gatherers(tmp_path, monkeypatch, gatherers):
    from app.config import settings
    from app.intake import IntakeSettings, save

    monkeypatch.setattr(settings, "intake_file", str(tmp_path / "intake.yaml"))
    save(IntakeSettings(gatherers=gatherers))


def _event(title, **kwargs):
    return ScrapedEvent(uid="u1", title=title, **kwargs)


#region: assign (default_categories)
def test_default_categories_apply_as_assign(tmp_path):
    cfg = _cfg(default_categories=["art"])
    events = [_event("One", categories=["workshop"])]
    apply(cfg, events)
    assert events[0].categories == ["intake:art", "intake:workshop"]


def test_no_defaults_no_change(tmp_path):
    events = [_event("One", categories=["workshop"])]
    apply(_cfg(), events)
    assert events[0].categories == ["intake:workshop"]
#endregion


#region: regex
def test_regex_matches_title(tmp_path):
    cfg = _cfg(rules=[CategoryRule(mode="regex", fields=["title"], regex="(?i)workshop", categories=["workshop"])])
    events = [_event("A pottery workshop"), _event("A concert")]
    apply(cfg, events)
    assert events[0].categories == ["intake:workshop"]
    assert events[1].categories == []


def test_regex_matches_any_of_multiple_fields(tmp_path):
    cfg = _cfg(rules=[CategoryRule(mode="regex", fields=["title", "description"], regex="(?i)open mic", categories=["music"])])
    events = [_event("Some title", description="Come to the open mic night")]
    apply(cfg, events)
    assert events[0].categories == ["intake:music"]


def test_regex_wildcard_fields(tmp_path):
    cfg = _cfg(rules=[CategoryRule(mode="regex", fields=["*"], regex="(?i)gall?ery", categories=["art"])])
    events = [_event("Some title", url="https://x/gallery/1")]
    apply(cfg, events)
    assert events[0].categories == ["intake:art"]


def test_regex_no_match(tmp_path):
    cfg = _cfg(rules=[CategoryRule(mode="regex", fields=["title"], regex="(?i)workshop", categories=["workshop"])])
    events = [_event("A concert")]
    apply(cfg, events)
    assert events[0].categories == []


def test_regex_accumulates_with_defaults(tmp_path):
    cfg = _cfg(
        default_categories=["art"],
        rules=[CategoryRule(mode="regex", fields=["title"], regex="(?i)workshop", categories=["workshop"])],
    )
    events = [_event("A workshop")]
    apply(cfg, events)
    assert events[0].categories == ["intake:art", "intake:workshop"]


def test_rules_apply_in_order(tmp_path):
    cfg = _cfg(
        rules=[
            CategoryRule(mode="assign", categories=["first"]),
            CategoryRule(mode="regex", fields=["title"], regex="(?i)workshop", categories=["second"]),
        ]
    )
    events = [_event("A workshop")]
    apply(cfg, events)
    assert events[0].categories == ["intake:first", "intake:second"]
#endregion


#region: gatherer scope
def test_gatherer_rules_apply(tmp_path, monkeypatch):
    _set_gatherers(
        tmp_path, monkeypatch,
        {"elfsight": GathererConfig(priority=5, rules=[CategoryRule(mode="regex", fields=["title"], regex="(?i)workshop", categories=["workshop"])])},
    )
    events = [_event("A pottery workshop")]
    apply(_cfg(), events)
    assert events[0].categories == ["intake:workshop"]


def test_gatherer_and_source_rules_both_apply(tmp_path, monkeypatch):
    _set_gatherers(
        tmp_path, monkeypatch,
        {"elfsight": GathererConfig(rules=[CategoryRule(mode="assign", categories=["gatherer-tag"])])},
    )
    cfg = _cfg(rules=[CategoryRule(mode="assign", categories=["source-tag"])])
    events = [_event("One")]
    apply(cfg, events)
    assert events[0].categories == ["intake:gatherer-tag", "intake:source-tag"]


def test_unrelated_gatherer_rules_do_not_apply(tmp_path, monkeypatch):
    _set_gatherers(
        tmp_path, monkeypatch,
        {"other": GathererConfig(rules=[CategoryRule(mode="assign", categories=["nope"])])},
    )
    events = [_event("One")]
    apply(_cfg(), events)
    assert events[0].categories == []
#endregion


#region: before-hash guarantee (integration)
def test_rule_change_reclassifies_events(tmp_path):
    from sqlmodel import Session, SQLModel, create_engine, select

    from app.decisionmaker import apply as decide
    from app.identity import stable_id
    from app.ingest import process_source
    from app.models import Event, Source

    engine = create_engine(f"sqlite:///{tmp_path / 'recat.db'}")
    SQLModel.metadata.create_all(engine)

    def run_fn(cfg):
        from app.schema import GathererResult

        return GathererResult(source=cfg, events=[ScrapedEvent(uid="u1", title="A workshop")])

    # first ingest: no rules -> no categories
    with Session(engine) as session:
        process_source(session, _cfg(), run_fn)
        session.commit()
    with Session(engine) as session:
        row = session.get(Event, stable_id("Test", ScrapedEvent(uid="u1", title="A workshop")))
        assert row.categories == ""

    # second ingest: add a regex rule -> event should be re-classified (updated)
    cfg = _cfg(rules=[CategoryRule(mode="regex", fields=["title"], regex="(?i)workshop", categories=["workshop"])])
    with Session(engine) as session:
        sieved, report = process_source(session, cfg, run_fn)
        session.commit()
    assert len(sieved.updated) == 1
    assert "categories" in sieved.updated[0].changed_fields
    with Session(engine) as session:
        row = session.get(Event, stable_id("Test", ScrapedEvent(uid="u1", title="A workshop")))
        assert row.categories == "intake:workshop"
#endregion
