"""Tests for category classification (F46), symlinks (F26), and identity (F51)."""
#region: imports
from datetime import datetime

from app.intake import IntakeSettings, save
from app.services.categories import (
    DEFAULT_CLASS,
    category_class,
    expose,
    exposed_classes,
    qualify,
    resolve_categories,
    resolve_event_categories,
    slugify,
)
#endregion


def _configure(tmp_path, monkeypatch, definitions=None, symlinks=None, exposed=None):
    from app.config import settings

    monkeypatch.setattr(settings, "intake_file", str(tmp_path / "intake.yaml"))
    kwargs = {"category_definitions": definitions or {}, "category_symlinks": symlinks or {}}
    if exposed is not None:
        kwargs["exposed_classes"] = exposed
    save(IntakeSettings(**kwargs))


#region: slugify
def test_slugify_lowercases_spaces_and_drops_punctuation():
    assert slugify("Film Screenings") == "film-screenings"
    assert slugify("  Art & Culture ") == "art-culture"
    assert slugify("Live Music!") == "live-music"


def test_slugify_collapses_and_trims_dashes():
    assert slugify("a--b") == "a-b"
    assert slugify(" -leading- ") == "leading"
    assert slugify("---") == ""
    assert slugify("") == ""


def test_slugify_keeps_alnum_and_dashes():
    assert slugify("abc-123") == "abc-123"
#endregion


#region: class
def test_category_class_returns_configured_class(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, definitions={"external": ["art", "music"]})
    assert category_class("art") == "external"
    assert category_class("ART") == "external"  # slug lookup
    assert category_class("music") == "external"


def test_category_class_defaults_to_intake(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, definitions={"external": ["art"]})
    assert category_class("unlisted-thing") == "intake"
    assert DEFAULT_CLASS == "intake"


def test_category_class_empty_registry(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    assert category_class("anything") == "intake"
#endregion


#region: qualify
def test_qualify_produces_class_name(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, definitions={"external": ["art"]})
    assert qualify("art") == "external:art"
    assert qualify("Film Screenings") == "intake:film-screenings"
    assert qualify("Art") == "external:art"
#endregion


#region: symlinks
def test_resolve_categories_maps_and_passes_through():
    links = {"intake:art-exhibition": "external:art", "intake:visual-arts": "external:art"}
    assert resolve_categories(
        ["intake:art-exhibition", "external:music", "intake:visual-arts"], links
    ) == ["external:art", "external:music"]


def test_resolve_categories_dedupes_and_sorts():
    links = {"intake:a": "external:x", "intake:b": "external:x"}
    assert resolve_categories(["intake:b", "intake:a", "external:x"], links) == ["external:x"]


def test_resolve_categories_empty():
    assert resolve_categories([]) == []


def test_resolve_event_categories_splits_and_resolves(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, symlinks={"intake:art-exhibition": "external:art"})
    assert resolve_event_categories("intake:art-exhibition,external:music") == ["external:art", "external:music"]


def test_resolve_event_categories_empty(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    assert resolve_event_categories("") == []
    assert resolve_event_categories(None) == []
#endregion


#region: exposure
def test_exposed_classes_defaults_to_external(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, definitions={"external": ["art"]})
    assert exposed_classes() == frozenset({"external"})


def test_expose_keeps_only_exposed_classes(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, exposed=["external"])
    assert expose(["external:art", "intake:raw", "external:music"]) == ["external:art", "external:music"]
    assert expose(["intake:raw", "intake:other"]) == []


def test_resolve_event_categories_filters_internal(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, symlinks={"intake:visual-arts": "external:art"})
    assert resolve_event_categories("intake:visual-arts,intake:unsymlinked,external:music") == [
        "external:art",
        "external:music",
    ]


def test_resolve_event_categories_internal_only_returns_empty(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    assert resolve_event_categories("intake:unsymlinked") == []


def test_expose_respects_custom_exposed_classes(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, exposed=["intake"])
    assert expose(["external:art", "intake:raw"]) == ["intake:raw"]
#endregion


#region: integration
def _event(categories):
    from app.models import Event

    return Event(id="e1", source_id=1, title="T", categories=categories, start_at=datetime(2030, 1, 1))


def test_serializer_resolves_symlinks(tmp_path, monkeypatch):
    from app.serializers import to_fullcalendar

    _configure(tmp_path, monkeypatch, symlinks={"intake:art-exhibition": "external:art"})
    payload = to_fullcalendar(_event("intake:art-exhibition,external:music"))
    assert payload["extendedProps"]["categories"] == ["external:art", "external:music"]


def test_query_events_filter_resolves_symlinks(tmp_path, monkeypatch):
    from sqlmodel import Session, SQLModel, create_engine

    from app.services.events import query_events

    engine = create_engine(f"sqlite:///{tmp_path / 'filter.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_event("intake:art-exhibition"))
        session.commit()

    _configure(tmp_path, monkeypatch, symlinks={"intake:art-exhibition": "external:art"})
    with Session(engine) as session:
        assert len(query_events(session, category="external:art")) == 1
        assert query_events(session, category="intake:art-exhibition") == []


def test_ics_resolves_symlinks(tmp_path, monkeypatch):
    from app.services.ics import event_to_vevent

    _configure(tmp_path, monkeypatch, symlinks={"intake:art-exhibition": "external:art"})
    ical = event_to_vevent(_event("intake:art-exhibition,external:music")).to_ical().decode()
    assert "CATEGORIES:external:art,external:music" in ical


def test_serializer_filters_internal_categories(tmp_path, monkeypatch):
    from app.serializers import to_fullcalendar

    _configure(tmp_path, monkeypatch, symlinks={"intake:art-exhibition": "external:art"})
    payload = to_fullcalendar(_event("intake:art-exhibition,intake:unsymlinked"))
    assert payload["extendedProps"]["categories"] == ["external:art"]


def test_query_events_filter_internal_returns_nothing(tmp_path, monkeypatch):
    from sqlmodel import Session, SQLModel, create_engine

    from app.services.events import query_events

    engine = create_engine(f"sqlite:///{tmp_path / 'filter2.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_event("intake:unsymlinked"))
        session.commit()

    _configure(tmp_path, monkeypatch)
    with Session(engine) as session:
        assert query_events(session, category="intake:unsymlinked") == []


def test_ics_filters_internal_categories(tmp_path, monkeypatch):
    from app.services.ics import event_to_vevent

    _configure(tmp_path, monkeypatch, symlinks={"intake:art-exhibition": "external:art"})
    ical = event_to_vevent(_event("intake:art-exhibition,intake:unsymlinked")).to_ical().decode()
    assert "CATEGORIES:external:art" in ical
    assert "intake:unsymlinked" not in ical


def test_debug_categories_show_symlink(tmp_path, monkeypatch, session_headers):
    import app.routers.debug as debug_router_mod
    from sqlmodel import Session, SQLModel, create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'debug.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_event("intake:art-exhibition"))
        session.commit()

    monkeypatch.setattr("app.services.actions.engine", engine)
    _configure(tmp_path, monkeypatch, symlinks={"intake:art-exhibition": "external:art"})

    from robyn.testing import TestClient

    from app.admin import app

    r = TestClient(app).get("/debug", headers=session_headers)
    assert r.status_code == 200
    assert "→ external:art" in r.text
#endregion
