"""Tests for the archive (GC) service (F22 + F22.01)."""
#region: imports
from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings
from app.models import Event, Source
from app.schema import ImageRef, dump_images, load_images
from app.services.archive import DEFAULT_ARCHIVE_LIMIT, archive, list_archived, restore
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


def _add(session, source_id, eid, start, end=None, last_seen_at=None, archived_at=None, archived_reason=None, pinned=False):
    session.add(
        Event(
            id=eid, source_id=source_id, title=eid, start_at=start, end_at=end,
            last_seen_at=last_seen_at, archived_at=archived_at, archived_reason=archived_reason,
            pinned=pinned,
        )
    )
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


#region: listing + restore (F22.02)
def test_list_archived_orders_most_recent_first(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch, past_days=None, grace_hours=None)
    with Session(engine) as session:
        sid = _source(session, NOW)
        _add(session, sid, "older", start=NOW - timedelta(days=1), archived_at=datetime(2026, 9, 10))
        _add(session, sid, "newer", start=NOW - timedelta(days=2), archived_at=datetime(2026, 9, 14))
        _add(session, sid, "mid", start=NOW - timedelta(days=3), archived_at=datetime(2026, 9, 12))

    with Session(engine) as session:
        rows = list_archived(session)

    assert [r["id"] for r in rows] == ["newer", "mid", "older"]


def test_list_archived_caps_by_limit(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch, past_days=None, grace_hours=None)
    with Session(engine) as session:
        sid = _source(session, NOW)
        for i in range(5):
            _add(session, sid, f"e{i}", start=NOW - timedelta(days=i), archived_at=NOW - timedelta(days=i))

    with Session(engine) as session:
        assert len(list_archived(session, limit=2)) == 2
        assert len(list_archived(session, limit=None)) == 5


def test_list_archived_includes_pinned(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch, past_days=None, grace_hours=None)
    with Session(engine) as session:
        sid = _source(session, NOW)
        _add(session, sid, "p", start=NOW - timedelta(days=1), archived_at=NOW, archived_reason="removed", pinned=True)

    with Session(engine) as session:
        rows = list_archived(session)

    assert rows[0]["pinned"] is True


def test_restore_unarchives(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch, past_days=None, grace_hours=None)
    with Session(engine) as session:
        sid = _source(session, NOW)
        _add(session, sid, "a", start=NOW + timedelta(days=1), archived_at=NOW, archived_reason="removed")

    with Session(engine) as session:
        assert restore(session, "a") is True
        session.commit()

    with Session(engine) as session:
        e = session.get(Event, "a")
        assert e.archived_at is None
        assert e.archived_reason is None


def test_restore_returns_false_when_not_archived(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch, past_days=None, grace_hours=None)
    with Session(engine) as session:
        sid = _source(session, NOW)
        _add(session, sid, "live", start=NOW + timedelta(days=1))

    with Session(engine) as session:
        assert restore(session, "live") is False
        assert restore(session, "nope") is False


def test_restore_rehosts_missing_images(tmp_path, monkeypatch):
    from app.services import images as images_mod

    engine = _setup(tmp_path, monkeypatch, past_days=None, grace_hours=None)
    missing = "f" * 64 + ".jpg"  # not on disk
    with Session(engine) as session:
        sid = _source(session, NOW)
        session.add(
            Event(
                id="a", source_id=sid, title="A",
                start_at=NOW + timedelta(days=1), archived_at=NOW, archived_reason="removed",
                images=dump_images([ImageRef(url=f"/images/{missing}", source_url="https://cdn.example/a.jpg")]),
            )
        )
        session.commit()

    with Session(engine) as session:
        assert restore(session, "a") is True
        session.commit()

    with Session(engine) as session:
        e = session.get(Event, "a")
        assert e.archived_at is None
        img = load_images(e.images)[0]
        assert img.url.startswith("/images/")
        assert img.url != f"/images/{missing}"
        assert images_mod.is_local(img.url) is True


def test_event_dump_includes_archive_fields(tmp_path):
    from app.services import stats

    engine = create_engine(f"sqlite:///{tmp_path / 'dump.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(
            Event(
                id="a", source_id=src.id, title="A",
                last_seen_at=datetime(2026, 9, 1), archived_at=datetime(2026, 9, 10), archived_reason="expired",
                pinned=True,
            )
        )
        session.commit()

    with Session(engine) as session:
        dump = stats.event_dump(session, "a")

    assert dump["last_seen_at"] == "2026-09-01T00:00:00"
    assert dump["archived_at"] == "2026-09-10T00:00:00"
    assert dump["archived_reason"] == "expired"
    assert dump["pinned"] is True


def test_default_archive_limit_matches_events_default():
    from app.services.events import DEFAULT_LIMIT

    assert DEFAULT_ARCHIVE_LIMIT == DEFAULT_LIMIT


def test_archive_still_archives_pinned_expired(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch, past_days=30)
    with Session(engine) as session:
        sid = _source(session, NOW)
        _add(session, sid, "pinned-old", start=NOW - timedelta(days=41), end=NOW - timedelta(days=40), last_seen_at=NOW, pinned=True)

    with Session(engine) as session:
        result = archive(session, now=NOW, dry_run=False)
        session.commit()

    assert result["expired"] == 1
    with Session(engine) as session:
        e = session.get(Event, "pinned-old")
        assert e.archived_at is not None
        assert e.archived_reason == "expired"
        assert e.pinned is True


def test_archive_is_idempotent(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch, past_days=30)
    with Session(engine) as session:
        sid = _source(session, NOW)
        _add(session, sid, "old", start=NOW - timedelta(days=41), end=NOW - timedelta(days=40), last_seen_at=NOW)

    with Session(engine) as session:
        first = archive(session, now=NOW, dry_run=False)
        session.commit()
    with Session(engine) as session:
        second = archive(session, now=NOW, dry_run=False)
        session.commit()

    assert first["expired"] == 1
    assert second["expired"] == 0
    assert second["removed"] == 0


def test_archive_uses_debug_clock(tmp_path, monkeypatch):
    from app.config import settings

    engine = _setup(tmp_path, monkeypatch, past_days=30)
    monkeypatch.setattr(settings, "debug_now", "2026-09-15T12:00:00")

    with Session(engine) as session:
        sid = _source(session, datetime(2026, 9, 15, 12, 0))
        _add(
            session, sid, "old",
            start=datetime(2026, 7, 31, 10, 0), end=datetime(2026, 8, 1, 10, 0),
            last_seen_at=datetime(2026, 9, 15, 12, 0),
        )

    with Session(engine) as session:
        result = archive(session, dry_run=False)  # no `now` -> uses the debug clock
        session.commit()

    assert result["expired"] == 1
    with Session(engine) as session:
        assert session.get(Event, "old").archived_at is not None
#endregion
