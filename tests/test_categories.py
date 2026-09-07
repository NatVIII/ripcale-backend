"""Tests for category classification (F46) and symlinks (F26)."""
#region: imports
from datetime import datetime

from app.intake import IntakeSettings, save
from app.services.categories import (
    DEFAULT_CLASS,
    EXTERNAL,
    INTAKE,
    category_class,
    resolve_categories,
    resolve_event_categories,
)
#endregion


def _configure(tmp_path, monkeypatch, classes=None, symlinks=None):
    from app.config import settings

    monkeypatch.setattr(settings, "intake_file", str(tmp_path / "intake.yaml"))
    save(IntakeSettings(category_definitions=classes or {}, category_symlinks=symlinks or {}))


def test_category_class_returns_external(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, {"external": ["art", "music"]})
    assert category_class("art") == EXTERNAL
    assert category_class("music") == EXTERNAL


def test_category_class_returns_intake(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, {"intake": ["art-exhibition"]})
    assert category_class("art-exhibition") == INTAKE


def test_category_class_defaults_to_intake(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, {"external": ["art"]})
    assert category_class("unlisted-thing") == INTAKE
    assert DEFAULT_CLASS == INTAKE


def test_category_class_empty_registry(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, {})
    assert category_class("anything") == INTAKE


def test_category_definitions_round_trip(tmp_path, monkeypatch):
    from app.config import settings
    from app.intake import load

    path = tmp_path / "intake.yaml"
    monkeypatch.setattr(settings, "intake_file", str(path))
    save(IntakeSettings(category_definitions={"external": ["art"], "intake": ["raw-stuff"]}))

    assert load().category_definitions == {"external": ["art"], "intake": ["raw-stuff"]}
    assert category_class("art") == EXTERNAL
    assert category_class("raw-stuff") == INTAKE
#endregion


#region: symlink resolver
def test_resolve_categories_maps_and_passes_through():
    links = {"art-exhibition": "art", "visual-arts": "art"}
    assert resolve_categories(["art-exhibition", "music", "visual-arts"], links) == ["art", "music"]


def test_resolve_categories_dedupes_and_sorts():
    links = {"a": "x", "b": "x"}
    assert resolve_categories(["b", "a", "x"], links) == ["x"]


def test_resolve_categories_empty():
    assert resolve_categories([]) == []


def test_resolve_event_categories_splits_and_resolves(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, symlinks={"art-exhibition": "art"})
    assert resolve_event_categories("art-exhibition,music") == ["art", "music"]


def test_resolve_event_categories_empty(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    assert resolve_event_categories("") == []
    assert resolve_event_categories(None) == []
#endregion


#region: integration
def _event(categories):
    from app.models import Event

    return Event(id="e1", source_id=1, title="T", categories=categories, start_at=datetime(2030, 1, 1))


def test_serializer_resolves_symlinks(tmp_path, monkeypatch):
    from app.serializers import to_fullcalendar

    _configure(tmp_path, monkeypatch, symlinks={"art-exhibition": "art"})
    payload = to_fullcalendar(_event("art-exhibition,music"))
    assert payload["extendedProps"]["categories"] == ["art", "music"]


def test_query_events_filter_resolves_symlinks(tmp_path, monkeypatch):
    from sqlmodel import Session, SQLModel, create_engine

    from app.services.events import query_events

    engine = create_engine(f"sqlite:///{tmp_path / 'filter.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_event("art-exhibition"))
        session.commit()

    _configure(tmp_path, monkeypatch, symlinks={"art-exhibition": "art"})
    with Session(engine) as session:
        assert len(query_events(session, category="art")) == 1
        assert query_events(session, category="art-exhibition") == []


def test_ics_resolves_symlinks(tmp_path, monkeypatch):
    from app.services.ics import event_to_vevent

    _configure(tmp_path, monkeypatch, symlinks={"art-exhibition": "art"})
    ical = event_to_vevent(_event("art-exhibition,music")).to_ical().decode()
    assert "CATEGORIES:art,music" in ical


def test_debug_categories_show_symlink(tmp_path, monkeypatch):
    import app.routers.debug as debug_router_mod
    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'debug.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_event("art-exhibition"))
        session.commit()

    monkeypatch.setattr(debug_router_mod, "engine", engine)
    _configure(tmp_path, monkeypatch, symlinks={"art-exhibition": "art"})

    from robyn.testing import TestClient

    from app.admin import app

    r = TestClient(app).get("/debug")
    assert r.status_code == 200
    assert "→ art" in r.text
#endregion
