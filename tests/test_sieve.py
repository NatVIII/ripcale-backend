from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

from app.identity import content_hash, stable_id
from app.models import Event, Source
from app.schema import ImageRef, GathererResult, ScrapedEvent, SourceConfig
from app.sieve import classify


def make_scraped(uid, title, start=datetime(2026, 9, 10, 18, 0)):
    return ScrapedEvent(uid=uid, title=title, start_at=start)


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
        sieved = classify(session, incoming)

    assert sieved.unchanged == 1
    assert len(sieved.new) == 1
    assert sieved.new[0].event.uid == "u3"
    assert len(sieved.updated) == 1
    assert sieved.updated[0].event.uid == "u2"
    assert sieved.updated[0].changed_fields == ["title"]


def test_classify_merges_default_categories(tmp_path):
    engine, source_id = _setup(tmp_path)
    cfg = SourceConfig(
        name="Test", gatherer="elfsight", url="https://x", default_categories=["art"]
    )

    incoming = GathererResult(
        source=cfg,
        events=[ScrapedEvent(uid="u1", title="One", categories=["workshop"])],
    )

    with Session(engine) as session:
        sieved = classify(session, incoming)

    assert sieved.new[0].event.categories == ["art", "workshop"]
    assert sieved.new[0].content_hash == content_hash(sieved.new[0].event)


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
        sieved = classify(session, incoming)

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
        sieved = classify(session, incoming)

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
        sieved = classify(session, incoming)

    assert len(sieved.updated) == 1
    assert "exdates" in sieved.updated[0].changed_fields
