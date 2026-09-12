from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

from app.identity import content_hash, stable_id
from app.models import Event, Source
from app.schema import ImageRef, GathererResult, ScrapedEvent, SourceConfig
from app.sieve import classify


def make_scraped(uid, title, start=datetime(2026, 9, 10, 18, 0)):
    return ScrapedEvent(uid=uid, title=title, start_at=start)


NOW = datetime(2026, 9, 15)


def _seed_event(session, source_id, event, source_name="Test"):
    session.add(
        Event(
            id=stable_id(source_name, event),
            source_id=source_id,
            uid=event.uid,
            title=event.title,
            start_at=event.start_at,
            content_hash=content_hash(event),
        )
    )


def _setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sieve.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        source = Source(name="Test", url="https://x")
        session.add(source)
        session.commit()
        session.refresh(source)
        source_id = source.id
    return engine, source_id


def test_classify_buckets(tmp_path):
    engine, source_id = _setup(tmp_path)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")

    with Session(engine) as session:
        _seed_event(session, source_id, make_scraped("u1", "One"))
        _seed_event(session, source_id, make_scraped("u2", "Two"))
        session.commit()

    incoming = GathererResult(
        source=cfg,
        events=[
            make_scraped("u1", "One"),        # unchanged
            make_scraped("u2", "Two Updated"),  # updated
            make_scraped("u3", "Three"),      # new
        ],
    )

    with Session(engine) as session:
        sieved = classify(session, incoming, now=NOW)

    assert sieved.unchanged == 1
    assert len(sieved.new) == 1
    assert sieved.new[0].event.uid == "u3"
    assert len(sieved.updated) == 1
    assert sieved.updated[0].event.uid == "u2"
    assert sieved.updated[0].changed_fields == ["title"]


def test_classify_images_change(tmp_path):
    engine, source_id = _setup(tmp_path)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")

    with Session(engine) as session:
        _seed_event(session, source_id, make_scraped("u1", "One"))
        session.commit()

    incoming = GathererResult(
        source=cfg,
        events=[ScrapedEvent(uid="u1", title="One", images=[ImageRef(url="https://x.com/a.jpg")])],
    )

    with Session(engine) as session:
        sieved = classify(session, incoming, now=NOW)

    assert len(sieved.updated) == 1
    assert "images" in sieved.updated[0].changed_fields


def test_classify_rrule_change(tmp_path):
    engine, source_id = _setup(tmp_path)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")

    with Session(engine) as session:
        _seed_event(session, source_id, make_scraped("u1", "One"))
        session.commit()

    incoming = GathererResult(
        source=cfg,
        events=[ScrapedEvent(uid="u1", title="One", rrule="FREQ=WEEKLY")],
    )

    with Session(engine) as session:
        sieved = classify(session, incoming, now=NOW)

    assert len(sieved.updated) == 1
    assert "rrule" in sieved.updated[0].changed_fields


def test_classify_exdates_change(tmp_path):
    engine, source_id = _setup(tmp_path)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")

    with Session(engine) as session:
        _seed_event(session, source_id, make_scraped("u1", "One"))
        session.commit()

    incoming = GathererResult(
        source=cfg,
        events=[ScrapedEvent(uid="u1", title="One", exdates=[datetime(2026, 9, 12, 18, 0)])],
    )

    with Session(engine) as session:
        sieved = classify(session, incoming, now=NOW)

    assert len(sieved.updated) == 1
    assert "exdates" in sieved.updated[0].changed_fields


#region: relevance (F13)
def _configure_expiry(monkeypatch, past=None, future=None):
    from app.config import settings

    monkeypatch.setattr(settings, "expire_past_days", past)
    monkeypatch.setattr(settings, "expire_future_days", future)


def test_relevance_drops_past_events(tmp_path, monkeypatch):
    engine, source_id = _setup(tmp_path)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")
    _configure_expiry(monkeypatch, past=10, future=None)

    old = ScrapedEvent(uid="old", title="Old", start_at=datetime(2026, 8, 1, 18, 0), end_at=datetime(2026, 8, 1, 20, 0))
    recent = ScrapedEvent(uid="recent", title="Recent", start_at=datetime(2026, 9, 14, 18, 0), end_at=datetime(2026, 9, 14, 20, 0))

    with Session(engine) as session:
        sieved = classify(session, GathererResult(source=cfg, events=[old, recent]), now=NOW)

    assert sieved.dropped == 1
    assert [c.event.uid for c in sieved.new] == ["recent"]


def test_relevance_drops_far_future_events(tmp_path, monkeypatch):
    engine, source_id = _setup(tmp_path)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")
    _configure_expiry(monkeypatch, past=None, future=30)

    far = ScrapedEvent(uid="far", title="Far", start_at=datetime(2027, 1, 1, 18, 0))
    soon = ScrapedEvent(uid="soon", title="Soon", start_at=datetime(2026, 9, 20, 18, 0))

    with Session(engine) as session:
        sieved = classify(session, GathererResult(source=cfg, events=[far, soon]), now=NOW)

    assert sieved.dropped == 1
    assert [c.event.uid for c in sieved.new] == ["soon"]


def test_relevance_unbounded_rrule_never_expires(tmp_path, monkeypatch):
    engine, source_id = _setup(tmp_path)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")
    _configure_expiry(monkeypatch, past=10, future=None)

    recurring = ScrapedEvent(uid="r", title="R", start_at=datetime(2020, 1, 1, 18, 0), rrule="FREQ=WEEKLY")

    with Session(engine) as session:
        sieved = classify(session, GathererResult(source=cfg, events=[recurring]), now=NOW)

    assert sieved.dropped == 0
    assert [c.event.uid for c in sieved.new] == ["r"]


def test_relevance_bounded_rrule_past_expires(tmp_path, monkeypatch):
    engine, source_id = _setup(tmp_path)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")
    _configure_expiry(monkeypatch, past=10, future=None)

    finished = ScrapedEvent(
        uid="r",
        title="R",
        start_at=datetime(2024, 1, 1, 18, 0),
        end_at=datetime(2024, 1, 1, 20, 0),
        rrule="FREQ=WEEKLY;UNTIL=20240129T000000",
    )

    with Session(engine) as session:
        sieved = classify(session, GathererResult(source=cfg, events=[finished]), now=NOW)

    assert sieved.dropped == 1


def test_relevance_bounded_rrule_recent_kept(tmp_path, monkeypatch):
    engine, source_id = _setup(tmp_path)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")
    _configure_expiry(monkeypatch, past=10, future=None)

    ongoing = ScrapedEvent(
        uid="r",
        title="R",
        start_at=datetime(2026, 9, 1, 18, 0),
        end_at=datetime(2026, 9, 1, 20, 0),
        rrule="FREQ=WEEKLY;UNTIL=20260913T000000",
    )

    with Session(engine) as session:
        sieved = classify(session, GathererResult(source=cfg, events=[ongoing]), now=NOW)

    assert sieved.dropped == 0


def test_relevance_null_dates_kept(tmp_path, monkeypatch):
    engine, source_id = _setup(tmp_path)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")
    _configure_expiry(monkeypatch, past=10, future=30)

    undated = ScrapedEvent(uid="u", title="U")

    with Session(engine) as session:
        sieved = classify(session, GathererResult(source=cfg, events=[undated]), now=NOW)

    assert sieved.dropped == 0
    assert [c.event.uid for c in sieved.new] == ["u"]


def test_relevance_disabled_is_pass_through(tmp_path, monkeypatch):
    engine, source_id = _setup(tmp_path)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")
    _configure_expiry(monkeypatch, past=None, future=None)

    old = ScrapedEvent(uid="old", title="Old", start_at=datetime(2020, 1, 1, 18, 0))

    with Session(engine) as session:
        sieved = classify(session, GathererResult(source=cfg, events=[old]), now=NOW)

    assert sieved.dropped == 0
    assert [c.event.uid for c in sieved.new] == ["old"]
#endregion
