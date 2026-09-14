import json
from pathlib import Path

import app.gatherers.elfsight.gatherer as elfsight_gatherer
from sqlmodel import Session, SQLModel, create_engine, select

from app.ingest import process_source
from app.models import Event
from app.schema import GathererConfig, SourceConfig

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "elfsight_boot.json").read_text())


def _cfg():
    return SourceConfig(
        name="Studio Two Three",
        gatherer="elfsight",
        url="https://fake/boot/?w=24ddbed9-c732-4102-abd2-02990fae125b",
    )


def test_ingest_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(elfsight_gatherer, "fetch_json", lambda url: FIXTURE)

    engine = create_engine(f"sqlite:///{tmp_path / 'ingest.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        sieved, report = process_source(session, _cfg(), elfsight_gatherer.run)
        session.commit()

    assert report == {"inserted": 3, "updated": 0, "unchanged": 0, "removed": 0}

    with Session(engine) as session:
        assert len(session.exec(select(Event)).all()) == 3

    with Session(engine) as session:
        sieved2, report2 = process_source(session, _cfg(), elfsight_gatherer.run)
        session.commit()

    assert sieved2.unchanged == 3
    assert len(sieved2.new) == 0
    assert len(sieved2.updated) == 0
    assert report2 == {"inserted": 0, "updated": 0, "unchanged": 3, "removed": 0}

    with Session(engine) as session:
        assert len(session.exec(select(Event)).all()) == 3


def test_source_priority(tmp_path, monkeypatch):
    from app.config import settings
    from app.intake import IntakeSettings, save
    from app.registry import source_priority

    monkeypatch.setattr(settings, "intake_file", str(tmp_path / "intake.yaml"))

    # source override wins
    cfg = SourceConfig(name="S", gatherer="elfsight", url="x", priority=8)
    assert source_priority(cfg) == 8

    # gatherer default
    save(IntakeSettings(gatherers={"elfsight": GathererConfig(priority=5)}))
    cfg2 = SourceConfig(name="S", gatherer="elfsight", url="x")
    assert source_priority(cfg2) == 5

    # fallback 0 (gatherer not configured)
    save(IntakeSettings(gatherers={}))
    assert source_priority(cfg2) == 0


def test_ingest_auto_runs_archive(tmp_path, monkeypatch):
    import app.ingest as ingest_mod
    from app.config import settings
    from app.schema import GathererResult, ScrapedEvent

    engine = create_engine(f"sqlite:///{tmp_path / 'ingest_auto.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ingest_mod, "engine", engine)
    monkeypatch.setattr(ingest_mod, "init_db", lambda: None)
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))

    cfg = SourceConfig(name="Good", gatherer="elfsight", url="https://x")
    monkeypatch.setattr(ingest_mod, "load_sources", lambda: [cfg])

    calls = []
    def fake_archive(session, dry_run):
        calls.append(dry_run)
        return {"expired": 0, "removed": 0, "dry_run": dry_run, "preview": []}

    monkeypatch.setattr(ingest_mod, "archive_service", fake_archive)
    monkeypatch.setattr(ingest_mod, "load_gatherer", lambda name: (lambda c: GathererResult(source=c, events=[ScrapedEvent(uid="u1", title="Event")])))

    ingest_mod.run(dry_run=False)
    assert calls == [False]

    calls.clear()
    ingest_mod.run(dry_run=True)
    assert calls == []


def test_archive_lifecycle_end_to_end(tmp_path, monkeypatch):
    import app.ingest as ingest_mod
    from datetime import timedelta

    from app.config import settings
    from app.models import Source, utcnow
    from app.schema import GathererResult
    from app.services import archive
    from app.services.events import query_events

    engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ingest_mod, "engine", engine)
    monkeypatch.setattr(ingest_mod, "init_db", lambda: None)
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "expire_past_days", 1)

    now = utcnow()
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(
            Event(
                id="old", source_id=src.id, title="Old",
                start_at=now - timedelta(days=3), end_at=now - timedelta(days=2),
                last_seen_at=now - timedelta(days=3),
            )
        )
        session.commit()

    cfg = SourceConfig(name="S", gatherer="elfsight", url="https://x")
    monkeypatch.setattr(ingest_mod, "load_sources", lambda: [cfg])
    monkeypatch.setattr(ingest_mod, "load_gatherer", lambda name: (lambda c: GathererResult(source=c, events=[])))

    ingest_mod.run(dry_run=False)

    with Session(engine) as session:
        e = session.get(Event, "old")
        assert e.archived_at is not None
        assert e.archived_reason == "expired"
        assert "old" not in [ev.id for ev in query_events(session)]

    with Session(engine) as session:
        assert archive.restore(session, "old") is True
        session.commit()

    with Session(engine) as session:
        assert "old" in [ev.id for ev in query_events(session)]


def test_pinned_event_content_preserved(tmp_path):
    from datetime import datetime

    from app.identity import content_hash, stable_id
    from app.models import Source
    from app.schema import GathererResult, ScrapedEvent

    engine = create_engine(f"sqlite:///{tmp_path / 'pin_e2e.db'}")
    SQLModel.metadata.create_all(engine)

    original = ScrapedEvent(uid="u1", title="Original", start_at=datetime(2030, 1, 1, 18, 0))
    eid = stable_id("Test", original)
    with Session(engine) as session:
        src = Source(name="Test", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(
            Event(
                id=eid, source_id=src.id, uid="u1", title="Original",
                start_at=original.start_at, content_hash=content_hash(original), pinned=True,
            )
        )
        session.commit()

    cfg = SourceConfig(name="Test", gatherer="elfsight", url="https://x")
    changed = ScrapedEvent(uid="u1", title="Changed", start_at=datetime(2030, 1, 1, 18, 0))
    run_fn = lambda c: GathererResult(source=c, events=[changed])

    with Session(engine) as session:
        process_source(session, cfg, run_fn)
        session.commit()

    with Session(engine) as session:
        e = session.get(Event, eid)
        src = session.get(Source, e.source_id)
        assert e.title == "Original"
        assert e.content_hash == content_hash(original)
        assert e.last_seen_at == src.last_fetched_at
