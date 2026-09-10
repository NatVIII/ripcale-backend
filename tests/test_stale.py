"""Tests for stale/removal detection (F15)."""
#region: imports
from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine, select

from app.decisionmaker import apply
from app.identity import content_hash, stable_id
from app.ingest import process_source
from app.models import Event, Source
from app.schema import GathererResult, ScrapedEvent, SourceConfig
from app.services.stats import stale_events
from app.sieve import classify
#endregion


CFG = SourceConfig(name="Test", gatherer="elfsight", url="https://x")


def make_scraped(uid, title, start=datetime(2026, 9, 10, 18, 0)):
    return ScrapedEvent(uid=uid, title=title, start_at=start)


def _run_with(events):
    return lambda cfg: GathererResult(source=cfg, events=events)


def _setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'stale.db'}")
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_event(session, source_id, event, source_name="Test", last_seen_at=None):
    session.add(
        Event(
            id=stable_id(source_name, event),
            source_id=source_id,
            uid=event.uid,
            title=event.title,
            start_at=event.start_at,
            content_hash=content_hash(event),
            last_seen_at=last_seen_at,
        )
    )
#endregion


#region: sieve
def test_sieve_populates_unchanged_ids(tmp_path):
    engine = _setup(tmp_path)
    with Session(engine) as session:
        src = Source(name="Test", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        _seed_event(session, src.id, make_scraped("u1", "One"))
        _seed_event(session, src.id, make_scraped("u2", "Two"))
        session.commit()

    incoming = GathererResult(
        source=CFG,
        events=[
            make_scraped("u1", "One"),
            make_scraped("u2", "Two"),
            make_scraped("u3", "Three"),
        ],
    )
    with Session(engine) as session:
        sieved = classify(session, incoming)

    assert sieved.unchanged == 2
    assert set(sieved.unchanged_ids) == {
        stable_id("Test", make_scraped("u1", "One")),
        stable_id("Test", make_scraped("u2", "Two")),
    }
#endregion


#region: last_seen_at
def test_last_seen_at_set_on_seen_events(tmp_path):
    engine = _setup(tmp_path)
    with Session(engine) as session:
        process_source(session, CFG, _run_with([make_scraped("u1", "One"), make_scraped("u2", "Two")]))
        session.commit()

    with Session(engine) as session:
        rows = session.exec(select(Event)).all()
        assert len(rows) == 2
        assert all(row.last_seen_at is not None for row in rows)


def test_removed_detection_end_to_end(tmp_path):
    engine = _setup(tmp_path)

    # first ingest: three events, none removed
    with Session(engine) as session:
        _, report = process_source(
            session, CFG,
            _run_with([make_scraped("u1", "One"), make_scraped("u2", "Two"), make_scraped("u3", "Three")]),
        )
        session.commit()
    assert report["removed"] == 0

    # second ingest: drop u2
    with Session(engine) as session:
        _, report = process_source(
            session, CFG,
            _run_with([make_scraped("u1", "One"), make_scraped("u3", "Three")]),
        )
        session.commit()
    assert report["removed"] == 1

    with Session(engine) as session:
        src = session.exec(select(Source).where(Source.name == "Test")).first()
        kept = session.get(Event, stable_id("Test", make_scraped("u1", "One")))
        dropped = session.get(Event, stable_id("Test", make_scraped("u2", "Two")))
        assert kept.last_seen_at == src.last_fetched_at
        assert dropped.last_seen_at != src.last_fetched_at


def test_null_last_seen_at_detected_as_removed(tmp_path):
    engine = _setup(tmp_path)
    with Session(engine) as session:
        src = Source(name="Test", url="https://x", last_fetched_at=datetime(2026, 1, 1))
        session.add(src)
        session.commit()
        session.refresh(src)
        _seed_event(session, src.id, make_scraped("old", "Old"))  # last_seen_at = NULL
        session.commit()

    with Session(engine) as session:
        _, report = process_source(session, CFG, _run_with([make_scraped("new", "New")]))
        session.commit()
    assert report["removed"] == 1
#endregion


#region: stats service
def test_stale_events_service(tmp_path):
    engine = _setup(tmp_path)
    with Session(engine) as session:
        process_source(session, CFG, _run_with([make_scraped("u1", "One"), make_scraped("u2", "Two")]))
        session.commit()
    with Session(engine) as session:
        process_source(session, CFG, _run_with([make_scraped("u1", "One")]))
        session.commit()

    with Session(engine) as session:
        stale = stale_events(session)
    assert len(stale) == 1
    assert stale[0]["title"] == "Two"
    assert stale[0]["source"] == "Test"
#endregion


#region: route
def test_stale_route_renders(tmp_path, monkeypatch):
    import app.routers.debug as debug_router_mod

    engine = _setup(tmp_path)
    with Session(engine) as session:
        src = Source(name="S", url="https://x", last_fetched_at=datetime(2030, 1, 1))
        session.add(src)
        session.commit()
        session.refresh(src)
        e = make_scraped("u1", "Gone")
        session.add(
            Event(
                id=stable_id("S", e),
                source_id=src.id,
                uid=e.uid,
                title=e.title,
                start_at=e.start_at,
                content_hash=content_hash(e),
                last_seen_at=datetime(2020, 1, 1),
            )
        )
        session.commit()

    monkeypatch.setattr("app.services.actions.engine", engine)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)
    r = client.get("/debug/stale")
    assert r.status_code == 200
    assert "Gone" in r.text
#endregion
