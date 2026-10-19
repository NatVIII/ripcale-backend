"""Tests for pinned-event change conflicts (F68)."""
#region: imports
import json

from sqlmodel import Session, SQLModel, create_engine

from app.models import Event, EventConflict, Source
from app.schema import ScrapedEvent
from app.services import conflicts
#endregion


def _incoming(**kw):
    base = ScrapedEvent(uid="u1", title="New Title", location="New Location")
    for k, v in kw.items():
        setattr(base, k, v)
    return json.dumps(base.model_dump(mode="json", exclude={"raw"}))


def _setup(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'conflicts.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(conflicts, "engine", engine)
    return engine


def _seed(engine, *, conflict_id="c1", event_id="e1", incoming=None, changed_fields=None, pinned_title="Pinned Title"):
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(Event(id=event_id, source_id=src.id, uid="u1", title=pinned_title, pinned=True))
        session.add(
            EventConflict(
                id=conflict_id, event_id=event_id,
                incoming=incoming or _incoming(),
                changed_fields=json.dumps(changed_fields or ["title", "location"]),
            )
        )
        session.commit()


def test_list_conflicts(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    _seed(engine)
    rows = conflicts.list_conflicts()
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["event_id"] == "e1"


def test_resolve_ignore(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    _seed(engine)
    assert conflicts.resolve("c1", "ignore") is True
    with Session(engine) as session:
        assert session.get(EventConflict, "c1").status == "ignored"
        assert session.get(Event, "e1").title == "Pinned Title"  # unchanged


def test_resolve_apply(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    _seed(engine)
    assert conflicts.resolve("c1", "apply") is True
    with Session(engine) as session:
        assert session.get(EventConflict, "c1").status == "applied"
        event = session.get(Event, "e1")
        assert event.title == "New Title"
        assert event.location == "New Location"
        assert event.pinned is True  # stays pinned


def test_resolve_syncretize(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    _seed(engine)
    monkeypatch.setattr(conflicts.deepseek, "chat", lambda messages, **kw: '{"description": "merged desc"}')
    assert conflicts.resolve("c1", "syncretize") is True
    with Session(engine) as session:
        assert session.get(EventConflict, "c1").status == "merged"
        event = session.get(Event, "e1")
        assert event.description == "merged desc"
        assert event.title == "Pinned Title"  # title untouched (not in syncretize output)


def test_resolve_invalid(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    _seed(engine)
    assert conflicts.resolve("nope", "apply") is False   # unknown id
    assert conflicts.resolve("c1", "bogus") is False     # bad action
    assert conflicts.resolve("c1", "apply") is True      # valid
    assert conflicts.resolve("c1", "apply") is False     # already resolved
#endregion


#region: sieve detection
def test_sieve_detects_pinned_conflict(tmp_path):
    from app.identity import content_hash, stable_id
    from app.schema import GathererResult, SourceConfig
    from app.sieve import classify

    engine = create_engine(f"sqlite:///{tmp_path / 'sieve_conflict.db'}")
    SQLModel.metadata.create_all(engine)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")
    original = ScrapedEvent(uid="u1", title="One")

    with Session(engine) as session:
        src = Source(name="Test", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(
            Event(
                id=stable_id("Test", original), source_id=src.id, uid="u1",
                title="One", content_hash=content_hash(original), pinned=True,
            )
        )
        session.commit()

    with Session(engine) as session:
        sieved = classify(session, GathererResult(source=cfg, events=[ScrapedEvent(uid="u1", title="Two")]))

    assert sieved.unchanged == 0
    assert len(sieved.conflicts) == 1
    assert sieved.conflicts[0].changed_fields == ["title"]


def test_sieve_pinned_unchanged_is_not_a_conflict(tmp_path):
    from app.identity import content_hash, stable_id
    from app.schema import GathererResult, SourceConfig
    from app.sieve import classify

    engine = create_engine(f"sqlite:///{tmp_path / 'sieve_ok.db'}")
    SQLModel.metadata.create_all(engine)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")
    original = ScrapedEvent(uid="u1", title="One")

    with Session(engine) as session:
        src = Source(name="Test", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(
            Event(
                id=stable_id("Test", original), source_id=src.id, uid="u1",
                title="One", content_hash=content_hash(original), pinned=True,
            )
        )
        session.commit()

    with Session(engine) as session:
        sieved = classify(session, GathererResult(source=cfg, events=[original]))

    assert sieved.unchanged == 1
    assert sieved.conflicts == []
#endregion
