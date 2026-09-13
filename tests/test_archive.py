"""Tests for the archive (GC) service (F22 + F22.01)."""
#region: imports
from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings
from app.models import Event, Source
from app.services.archive import archive
#endregion


NOW = datetime(2026, 9, 15, 12, 0)


def _setup(tmp_path, monkeypatch, past_days=90, grace_hours=6):
    engine = create_engine(f"sqlite:///{tmp_path / 'archive.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(settings, "expire_past_days", past_days)
    monkeypatch.setattr(settings, "expire_future_days", None)
    monkeypatch.setattr(settings, "archive_grace_hours", grace_hours)
    return engine


def _source(session, fetched_at):
    src = Source(name="S", url="https://x", last_fetched_at=fetched_at)
    session.add(src)
    session.commit()
    session.refresh(src)
    return src.id


def _add(session, source_id, eid, start, end=None, last_seen_at=None):
    session.add(Event(id=eid, source_id=source_id, title=eid, start_at=start, end_at=end, last_seen_at=last_seen_at))
    session.commit()


#region: expired (immediate)
def test_archive_expired_immediate(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch, past_days=30)
    with Session(engine) as session:
        sid = _source(session, NOW)
        _add(session, sid, "old", start=NOW - timedelta(days=41), end=NOW - timedelta(days=40), last_seen_at=NOW)

    with Session(engine) as session:
        result = archive(session, now=NOW, dry_run=False)
        session.commit()

    assert result == {"expired": 1, "removed": 0, "dry_run": False, "preview": [{"id": "old", "title": "old", "reason": "expired"}]}
    with Session(engine) as session:
        e = session.get(Event, "old")
        assert e.archived_at == NOW
        assert e.archived_reason == "expired"


def test_archive_expired_dry_run_writes_nothing(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch, past_days=30)
    with Session(engine) as session:
        sid = _source(session, NOW)
        _add(session, sid, "old", start=NOW - timedelta(days=41), end=NOW - timedelta(days=40), last_seen_at=NOW)

    with Session(engine) as session:
        result = archive(session, now=NOW, dry_run=True)

    assert result["expired"] == 1
    with Session(engine) as session:
        assert session.get(Event, "old").archived_at is None
#endregion


#region: removed (grace)
def test_archive_removed_after_grace(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch, past_days=90, grace_hours=6)
    with Session(engine) as session:
        sid = _source(session, NOW)
        _add(session, sid, "within", start=NOW + timedelta(days=10), last_seen_at=NOW - timedelta(hours=2))
        _add(session, sid, "past", start=NOW + timedelta(days=10), last_seen_at=NOW - timedelta(hours=10))

    with Session(engine) as session:
        result = archive(session, now=NOW, dry_run=False)
        session.commit()

    assert result["removed"] == 1
    assert result["preview"] == [{"id": "past", "title": "past", "reason": "removed"}]
    with Session(engine) as session:
        assert session.get(Event, "within").archived_at is None
        assert session.get(Event, "past").archived_reason == "removed"


def test_archive_removed_grace_none_disables(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch, past_days=90, grace_hours=None)
    with Session(engine) as session:
        sid = _source(session, NOW)
        _add(session, sid, "gone", start=NOW + timedelta(days=10), last_seen_at=NOW - timedelta(days=5))

    with Session(engine) as session:
        result = archive(session, now=NOW, dry_run=False)
        session.commit()

    assert result["removed"] == 0
    assert result["expired"] == 0
#endregion


#region: expiry disabled
def test_archive_expired_disabled_still_removes_removed(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch, past_days=None, grace_hours=6)
    with Session(engine) as session:
        sid = _source(session, NOW)
        _add(session, sid, "old", start=NOW - timedelta(days=200), last_seen_at=NOW)  # seen this run -> not removed
        _add(session, sid, "gone", start=NOW + timedelta(days=10), last_seen_at=NOW - timedelta(days=5))

    with Session(engine) as session:
        result = archive(session, now=NOW, dry_run=False)
        session.commit()

    assert result["expired"] == 0
    assert result["removed"] == 1


def test_archive_null_last_seen_is_removed_eligible(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch, past_days=90, grace_hours=6)
    with Session(engine) as session:
        sid = _source(session, NOW)
        _add(session, sid, "never", start=NOW + timedelta(days=10), last_seen_at=None)

    with Session(engine) as session:
        result = archive(session, now=NOW, dry_run=False)
        session.commit()

    assert result["removed"] == 1
#endregion
