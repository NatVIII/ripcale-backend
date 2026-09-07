"""Contract compliance tests: the docs are the source of truth; code must match.

Each pipeline-stage contract doc carries a `Version: N` stamp; the stage module
declares `CONTRACT_VERSION = N`. These tests assert the code agrees with the doc
(version), that the pydantic shapes match the documented field sets, and that the
documented invariants hold.
"""
#region: imports
import re
from pathlib import Path

from app.schema import ClassifiedEvent, SieveResult
from app.sieve.sieve import CONTRACT_VERSION, _CHANGED_FIELDS
#endregion


#region: helpers
DOCS = Path(__file__).resolve().parents[1] / "docs"


def _read_version(doc_name: str) -> int:
    text = (DOCS / doc_name).read_text()
    match = re.search(r"^Version:\s*(\d+)\s*$", text, re.MULTILINE)
    assert match is not None, f"{doc_name}: missing `Version:` stamp"
    return int(match.group(1))
#endregion


#region: sieve contract — version + shapes
def test_sieve_version_matches_doc():
    assert CONTRACT_VERSION == _read_version("SIEVE_CONTRACT.md")


def test_sieve_result_fields_match_doc():
    assert set(SieveResult.model_fields) == {
        "source", "new", "updated", "unchanged", "unchanged_ids",
    }


def test_classified_event_fields_match_doc():
    assert set(ClassifiedEvent.model_fields) == {
        "id", "content_hash", "event", "changed_fields",
    }


def test_changed_fields_match_doc():
    assert set(_CHANGED_FIELDS) == {
        "title", "description", "location", "url", "images", "start_at",
        "end_at", "timezone", "all_day", "rrule", "exdates", "categories",
    }
#endregion


#region: sieve contract — invariants
def test_classify_is_read_only(tmp_path):
    from sqlmodel import Session, SQLModel, create_engine, select

    from app.identity import content_hash, stable_id
    from app.models import Event, Source
    from app.schema import GathererResult, ScrapedEvent, SourceConfig
    from app.sieve import classify

    engine = create_engine(f"sqlite:///{tmp_path / 'contract.db'}")
    SQLModel.metadata.create_all(engine)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")
    event = ScrapedEvent(uid="u1", title="One")

    with Session(engine) as session:
        src = Source(name="Test", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(
            Event(
                id=stable_id("Test", event),
                source_id=src.id,
                uid=event.uid,
                title=event.title,
                start_at=event.start_at,
                content_hash=content_hash(event),
            )
        )
        session.commit()

    with Session(engine) as session:
        sieved = classify(session, GathererResult(source=cfg, events=[event]))
        session.commit()
    assert sieved.unchanged == 1

    with Session(engine) as session:
        rows = session.exec(select(Event)).all()
        assert len(rows) == 1
        assert rows[0].content_hash == content_hash(event)


def test_classify_is_idempotent(tmp_path):
    from sqlmodel import Session, SQLModel, create_engine

    from app.schema import GathererResult, ScrapedEvent, SourceConfig
    from app.sieve import classify

    engine = create_engine(f"sqlite:///{tmp_path / 'idem.db'}")
    SQLModel.metadata.create_all(engine)
    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")
    incoming = GathererResult(source=cfg, events=[ScrapedEvent(uid="u1", title="One")])

    with Session(engine) as session:
        first = classify(session, incoming)
        second = classify(session, incoming)

    assert [c.id for c in first.new] == [c.id for c in second.new]
    assert [c.id for c in first.updated] == [c.id for c in second.updated]
    assert first.unchanged_ids == second.unchanged_ids
#endregion
