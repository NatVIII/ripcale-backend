from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

from app.decisionmaker import apply
from app.identity import content_hash, stable_id
from app.models import Event, Source
from app.schema import ClassifiedEvent, ScrapedEvent, SieveResult, SourceConfig


def make_scraped(uid, title, start=datetime(2026, 9, 10, 18, 0)):
    return ScrapedEvent(uid=uid, title=title, start_at=start)


def _classified(source_name, event, changed=None):
    return ClassifiedEvent(
        id=stable_id(source_name, event),
        content_hash=content_hash(event),
        event=event,
        changed_fields=changed or [],
    )


def test_apply_inserts_and_updates(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'decide.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        source = Source(name="Test", url="https://x")
        session.add(source)
        session.commit()
        session.refresh(source)
        source_id = source.id

        existing = make_scraped("u2", "Two")
        session.add(
            Event(
                id=stable_id("Test", existing),
                source_id=source_id,
                uid=existing.uid,
                title=existing.title,
                start_at=existing.start_at,
                content_hash=content_hash(existing),
            )
        )
        session.commit()

    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")
    sieved = SieveResult(
        source=cfg,
        new=[_classified("Test", make_scraped("u3", "Three"))],
        updated=[_classified("Test", make_scraped("u2", "Two Updated"), changed=["title"])],
    )

    with Session(engine) as session:
        source = session.get(Source, source_id)
        report = apply(session, source, sieved)
        session.commit()

    assert report == {"inserted": 1, "updated": 1, "unchanged": 0}

    with Session(engine) as session:
        three = session.get(Event, stable_id("Test", make_scraped("u3", "Three")))
        assert three.title == "Three"
        assert three.content_hash == content_hash(make_scraped("u3", "Three"))

        two = session.get(Event, stable_id("Test", make_scraped("u2", "Two Updated")))
        assert two.title == "Two Updated"
        assert two.content_hash == content_hash(make_scraped("u2", "Two Updated"))
