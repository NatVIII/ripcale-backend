"""Tests for app.services.actions (the shared admin operations)."""
#region: imports
import pytest
from sqlmodel import SQLModel, create_engine

from app.schema import CategoryRule
from app.services import actions
from app.services.actions import ActionError
#endregion


def _engine(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'actions.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("app.services.actions.engine", engine)
    monkeypatch.setattr("app.db.engine", engine)
    monkeypatch.setattr("app.ingest.engine", engine)
    return engine


#region: parsing
def test_resolve_source_spec_manual_sentinel(monkeypatch):
    cfg = actions.resolve_source_spec({"source": "manual", "gatherer": "elfsight", "url": "https://x"})
    assert cfg is not None
    assert cfg.gatherer == "elfsight"
    assert cfg.url == "https://x"


def test_resolve_source_spec_missing_fields(monkeypatch):
    assert actions.resolve_source_spec({"source": "manual"}) is None


def test_parse_rules_single_dict():
    rules = actions.parse_rules({"rules": {"mode": "assign", "categories": ["art"]}})
    assert rules == [CategoryRule(mode="assign", categories=["art"])]


def test_parse_rules_none():
    assert actions.parse_rules({}) is None
#endregion


#region: write actions
def test_retag_requires_from(tmp_path, monkeypatch):
    _engine(tmp_path, monkeypatch)
    with pytest.raises(ActionError):
        actions.retag("", "external:art")


def test_wipe_challenge_flow(tmp_path, monkeypatch):
    _engine(tmp_path, monkeypatch)
    challenge = actions.wipe_begin()
    assert isinstance(challenge, str) and challenge

    with pytest.raises(ActionError):
        actions.wipe_confirm("nope")

    result = actions.wipe_confirm(challenge)
    assert result == {"events": 0, "sources": 0}

    # challenge is consumed — a second use fails
    with pytest.raises(ActionError):
        actions.wipe_confirm(challenge)
#endregion


#region: category mapping
def test_category_mapping(tmp_path, monkeypatch):
    from sqlmodel import Session

    from app.config import settings
    from app.intake import IntakeSettings, save as save_intake
    from app.models import Event

    _engine(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "intake_file", str(tmp_path / "intake.yaml"))
    save_intake(
        IntakeSettings(
            category_definitions={"external": ["art"]},
            category_symlinks={"intake:raw": "external:art"},
            exposed_classes=["external"],
        )
    )

    with Session(actions.engine) as session:
        session.add(Event(id="e1", source_id=1, title="T", categories="external:art,intake:raw"))
        session.commit()

    mapping = actions.category_mapping()
    assert mapping["definitions"] == {"external": ["art"]}
    assert mapping["symlinks"] == {"intake:raw": "external:art"}
    assert mapping["exposed_classes"] == ["external"]

    by_name = {c["name"]: c for c in mapping["categories"]}
    assert by_name["external:art"]["class"] == "external"
    assert by_name["external:art"]["exposed"] is True
    assert by_name["intake:raw"]["class"] == "intake"
    assert by_name["intake:raw"]["exposed"] is False
#endregion


#region: editing (F28)
def test_edit_event_updates_and_returns_dump(tmp_path, monkeypatch):
    from datetime import datetime

    from sqlmodel import Session

    from app.models import Event, Source

    engine = _engine(tmp_path, monkeypatch)
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(Event(id="e", source_id=src.id, title="Old", start_at=datetime(2030, 1, 1)))
        session.commit()

    dump = actions.edit_event(
        "e",
        {"title": "New", "start_at": "2030-01-02T00:00:00", "categories": "external:art,intake:x", "pinned": True},
    )
    assert dump["title"] == "New"
    assert dump["start_at"] == "2030-01-02T00:00:00"
    assert dump["pinned"] is True
    assert dump["categories"] == "external:art,intake:x"

    with Session(engine) as session:
        assert session.get(Event, "e").title == "New"


def test_edit_event_bad_input(tmp_path, monkeypatch):
    from sqlmodel import Session

    from app.models import Event, Source

    engine = _engine(tmp_path, monkeypatch)
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(Event(id="e", source_id=src.id, title="Old"))
        session.commit()

    with pytest.raises(ActionError):
        actions.edit_event("e", {"start_at": "not-a-date"})

    with pytest.raises(ActionError):
        actions.edit_event("e", {"images": "not-json"})

    with pytest.raises(ActionError) as exc:
        actions.edit_event("nope", {"title": "X"})
    assert exc.value.status == 404
#endregion


#region: event list (F28.01)
def test_event_list_rows(tmp_path, monkeypatch):
    from datetime import datetime

    from sqlmodel import Session

    from app.models import Event, Source

    engine = _engine(tmp_path, monkeypatch)
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(Event(id="a", source_id=src.id, title="Alpha", start_at=datetime(2030, 1, 1), categories="external:art", pinned=True))
        session.add(Event(id="b", source_id=src.id, title="Beta", start_at=datetime(2029, 1, 1), categories="intake:raw"))
        session.commit()

    rows = actions.event_list()
    assert [r["id"] for r in rows] == ["a", "b"]  # start_at desc

    a = rows[0]
    assert a["title"] == "Alpha"
    assert a["source"] == "S"
    assert a["categories"] == "external:art"  # raw, not resolved
    assert a["pinned"] is True
    assert a["start_at"] == "2030-01-01T00:00:00"
    assert "America/New_York" in a["start_at_display"]
    assert "UTC" in a["start_at_display"]


def test_event_list_respects_limit_and_category(tmp_path, monkeypatch):
    from sqlmodel import Session

    from app.models import Event, Source

    engine = _engine(tmp_path, monkeypatch)
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(Event(id="a", source_id=src.id, title="A", categories="external:art"))
        session.add(Event(id="b", source_id=src.id, title="B", categories="external:music"))
        session.commit()

    assert len(actions.event_list(limit=1)) == 1
    assert [r["id"] for r in actions.event_list(category="external:music")] == ["b"]
#endregion
