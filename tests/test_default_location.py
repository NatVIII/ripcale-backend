"""Tests for the per-source default location (F32)."""
#region: imports
from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine, select

from app.identity import content_hash, stable_id
from app.ingest import process_source
from app.models import Event, Source
from app.schema import GathererResult, ScrapedEvent, SourceConfig
#endregion


def _cfg(default_location=None):
    return SourceConfig(name="Test", gatherer="elfsight", url="https://x", default_location=default_location)


def _setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'default_location.db'}")
    SQLModel.metadata.create_all(engine)
    return engine


def _run_with(events):
    return lambda cfg: GathererResult(source=cfg, events=events)


def _event(uid, location, title="T"):
    return ScrapedEvent(uid=uid, title=title, location=location, start_at=datetime(2026, 9, 10, 18, 0))
#endregion


#region: sieve merge
def test_blank_location_filled_with_default(tmp_path):
    from app.sieve import classify

    engine = _setup(tmp_path)
    cfg = _cfg(default_location="Richmond, VA")
    incoming = GathererResult(source=cfg, events=[_event("u1", None)])

    with Session(engine) as session:
        sieved = classify(session, incoming)

    assert sieved.new[0].event.location == "Richmond, VA"
    # the default participates in the content hash
    assert sieved.new[0].content_hash == content_hash(_event("u1", "Richmond, VA"))


def test_whitespace_location_filled_with_default(tmp_path):
    from app.sieve import classify

    engine = _setup(tmp_path)
    cfg = _cfg(default_location="Richmond, VA")
    incoming = GathererResult(source=cfg, events=[_event("u1", "   ")])

    with Session(engine) as session:
        sieved = classify(session, incoming)

    assert sieved.new[0].event.location == "Richmond, VA"


def test_existing_location_untouched(tmp_path):
    from app.sieve import classify

    engine = _setup(tmp_path)
    cfg = _cfg(default_location="Richmond, VA")
    incoming = GathererResult(source=cfg, events=[_event("u1", "A Real Venue")])

    with Session(engine) as session:
        sieved = classify(session, incoming)

    assert sieved.new[0].event.location == "A Real Venue"


def test_no_default_leaves_location_none(tmp_path):
    from app.sieve import classify

    engine = _setup(tmp_path)
    incoming = GathererResult(source=_cfg(), events=[_event("u1", None)])

    with Session(engine) as session:
        sieved = classify(session, incoming)

    assert sieved.new[0].event.location is None
#endregion


#region: end-to-end
def test_default_location_persists_to_event(tmp_path):
    engine = _setup(tmp_path)
    with Session(engine) as session:
        process_source(session, _cfg(default_location="Richmond, VA"), _run_with([_event("u1", None)]))
        session.commit()

    with Session(engine) as session:
        row = session.get(Event, stable_id("Test", _event("u1", None)))
        assert row.location == "Richmond, VA"
#endregion
