"""Decisionmaker contract compliance tests.

The decisionmaker contract lives in `docs/DECISIONMAKER_CONTRACT.md` (the source
of truth). These tests assert the code's declared version matches the doc, the
report shape, the `ScrapedEvent` → `Event` field mapping, and the documented
invariants.
"""
#region: imports
from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine, select

from app.decisionmaker import apply
from app.decisionmaker.decisionmaker import CONTRACT_VERSION
from app.identity import content_hash, stable_id
from app.models import Event, Source
from app.schema import (
    ClassifiedEvent,
    ImageRef,
    ScrapedEvent,
    SieveResult,
    SourceConfig,
    dump_exdates,
    dump_images,
)

from contract_helpers import read_contract_version
#endregion


#region: helpers
def _classified(source_name, event, changed=None):
    return ClassifiedEvent(
        id=stable_id(source_name, event),
        content_hash=content_hash(event),
        event=event,
        changed_fields=changed or [],
    )


def _setup(tmp_path, name="Test"):
    engine = create_engine(f"sqlite:///{tmp_path / 'decide_contract.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        src = Source(name=name, url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        source_id = src.id
    return engine, source_id


def _cfg(name="Test"):
    return SourceConfig(name=name, gatherer="elfsight", url="https://x")
#endregion


#region: version
def test_decisionmaker_version_matches_doc():
    assert CONTRACT_VERSION == read_contract_version("DECISIONMAKER_CONTRACT.md")
#endregion


#region: report shape
def test_apply_report_shape(tmp_path):
    engine, source_id = _setup(tmp_path)
    sieved = SieveResult(source=_cfg(), new=[_classified("Test", ScrapedEvent(uid="u1", title="One"))])

    with Session(engine) as session:
        source = session.get(Source, source_id)
        report = apply(session, source, sieved)
        session.commit()

    assert set(report) == {"inserted", "updated", "unchanged", "removed"}
#endregion


#region: field mapping
def test_apply_maps_all_fields(tmp_path):
    engine, source_id = _setup(tmp_path)

    start = datetime(2026, 9, 10, 18, 0)
    end = datetime(2026, 9, 10, 20, 0)
    rid = datetime(2026, 9, 11, 18, 0)
    exd = [datetime(2026, 9, 12, 18, 0)]
    event = ScrapedEvent(
        uid="u1",
        title="Title",
        description="<p>desc</p>",
        location="Venue",
        url="https://x/e",
        images=[ImageRef(url="https://x/a.jpg", alt="A", source_url="https://x/a0.jpg")],
        start_at=start,
        end_at=end,
        timezone="America/New_York",
        all_day=False,
        rrule="FREQ=WEEKLY",
        recurrence_id=rid,
        exdates=exd,
        categories=["b", "a", "a"],
    )
    classified = _classified("Test", event)
    sieved = SieveResult(source=_cfg(), new=[classified])

    with Session(engine) as session:
        source = session.get(Source, source_id)
        report = apply(session, source, sieved)
        session.commit()
    assert report == {"inserted": 1, "updated": 0, "unchanged": 0, "removed": 0}

    with Session(engine) as session:
        row = session.get(Event, classified.id)
        assert row.source_id == source_id
        assert row.uid == "u1"
        assert row.title == "Title"
        assert row.description == "<p>desc</p>"
        assert row.location == "Venue"
        assert row.url == "https://x/e"
        assert row.images == dump_images(event.images)
        assert row.start_at == start
        assert row.end_at == end
        assert row.timezone == "America/New_York"
        assert row.all_day is False
        assert row.rrule == "FREQ=WEEKLY"
        assert row.recurrence_id == rid
        assert row.exdates == dump_exdates(event.exdates)
        assert row.categories == "a,b"
        assert row.content_hash == classified.content_hash
        assert row.last_seen_at is not None
#endregion


#region: invariants
def test_apply_update_path_is_idempotent(tmp_path):
    engine, source_id = _setup(tmp_path)

    original = ScrapedEvent(uid="u1", title="One")
    with Session(engine) as session:
        session.add(
            Event(
                id=stable_id("Test", original),
                source_id=source_id,
                uid=original.uid,
                title=original.title,
                start_at=original.start_at,
                content_hash=content_hash(original),
            )
        )
        session.commit()

    changed = ScrapedEvent(uid="u1", title="One Updated")
    sieved = SieveResult(source=_cfg(), updated=[_classified("Test", changed, changed=["title"])])

    with Session(engine) as session:
        source = session.get(Source, source_id)
        apply(session, source, sieved)
        session.commit()

    with Session(engine) as session:
        source = session.get(Source, source_id)
        apply(session, source, sieved)
        session.commit()

    with Session(engine) as session:
        rows = session.exec(select(Event)).all()
        assert len(rows) == 1
        assert rows[0].title == "One Updated"
#endregion
