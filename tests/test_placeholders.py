"""Tests for declarative recurring placeholders (F66.02)."""
#region: imports
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Event, Source
from app.schema import RecurrenceConfig, SourceConfig
from app.services.placeholders import _series_uid, materialize
#endregion


def _decl(**kw):
    base = {
        "title": "Weekly Ride",
        "rrule": "FREQ=WEEKLY;BYDAY=MO",
        "start_at": "2026-10-19T18:30:00-04:00",
        "timezone": "America/New_York",
    }
    base.update(kw)
    return RecurrenceConfig(**base)


def _cfg(*decls):
    return SourceConfig(name="S", gatherer="hikerapi", url="https://x", recurrences=list(decls))


def _setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'placeholders.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        src = Source(name="S", url="https://x", gatherer="hikerapi")
        session.add(src)
        session.commit()
        session.refresh(src)
        sid = src.id
    return engine, sid


def test_materialize_creates_placeholder(tmp_path):
    engine, sid = _setup(tmp_path)
    with Session(engine) as session:
        src = session.get(Source, sid)
        result = materialize(session, src, _cfg(_decl()))
        session.commit()

    assert result == {"created": 1, "updated": 0, "archived": 0}
    with Session(engine) as session:
        event = session.exec(select(Event)).one()
        assert event.placeholder is True
        assert event.pinned is True
        assert event.rrule == "FREQ=WEEKLY;BYDAY=MO"
        assert event.title == "Weekly Ride"
        assert event.uid.startswith("recurrence:")


def test_materialize_is_idempotent(tmp_path):
    engine, sid = _setup(tmp_path)
    with Session(engine) as session:
        src = session.get(Source, sid)
        materialize(session, src, _cfg(_decl()))
        session.commit()
        result = materialize(session, src, _cfg(_decl()))
        session.commit()

    assert result == {"created": 0, "updated": 1, "archived": 0}
    with Session(engine) as session:
        assert len(session.exec(select(Event)).all()) == 1


def test_materialize_archives_removed(tmp_path):
    engine, sid = _setup(tmp_path)
    with Session(engine) as session:
        src = session.get(Source, sid)
        materialize(session, src, _cfg(_decl()))
        session.commit()
        result = materialize(session, src, _cfg())  # declaration nixed
        session.commit()

    assert result == {"created": 0, "updated": 0, "archived": 1}
    with Session(engine) as session:
        event = session.exec(select(Event)).one()
        assert event.archived_at is not None
        assert event.archived_reason == "removed"


def test_materialize_unarchives_when_redeclared(tmp_path):
    engine, sid = _setup(tmp_path)
    with Session(engine) as session:
        src = session.get(Source, sid)
        materialize(session, src, _cfg(_decl()))
        session.commit()
        materialize(session, src, _cfg())  # nix → archive
        session.commit()
        result = materialize(session, src, _cfg(_decl()))  # re-add
        session.commit()

    assert result == {"created": 0, "updated": 1, "archived": 0}
    with Session(engine) as session:
        event = session.exec(select(Event)).one()
        assert event.archived_at is None


def test_series_uid_is_stable():
    assert _series_uid("S", _decl()) == _series_uid("S", _decl())
    assert _series_uid("S", _decl()) != _series_uid("S", _decl(title="Other Ride"))
    assert _series_uid("S", _decl()) != _series_uid("T", _decl())
#endregion


#region: F66.03 — approval appliers
def _setup_intake(tmp_path, monkeypatch, *decls):
    from app.config import settings
    from app.intake import IntakeSettings, save
    from app.schema import SourceConfig

    monkeypatch.setattr(settings, "intake_file", str(tmp_path / "intake.yaml"))
    save(IntakeSettings(sources=[SourceConfig(name="S", gatherer="hikerapi", url="https://x", recurrences=list(decls))]))


def _setup_engine(tmp_path, monkeypatch):
    from app.services import approvals

    engine = create_engine(f"sqlite:///{tmp_path / 'db.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(approvals, "engine", engine)
    return engine


def test_add_recurrence_applier_writes_intake_and_materializes(tmp_path, monkeypatch):
    from app.intake import load
    from app.services import approvals

    _setup_intake(tmp_path, monkeypatch)
    engine = _setup_engine(tmp_path, monkeypatch)

    aid = approvals.create(
        "recurrence_add", source_name="S",
        payload={"title": "Weekly", "rrule": "FREQ=WEEKLY;BYDAY=MO", "start_at": "2026-10-19T18:30:00-04:00", "timezone": "America/New_York"},
        reason="weekly",
    )
    assert approvals.approve(aid) is True

    assert load().sources[0].recurrences[0].title == "Weekly"
    with Session(engine) as session:
        event = session.exec(select(Event)).one()
        assert event.placeholder is True
        assert event.rrule == "FREQ=WEEKLY;BYDAY=MO"


def test_remove_recurrence_applier_nixes_and_archives(tmp_path, monkeypatch):
    from app.intake import load
    from app.services import approvals

    _setup_intake(tmp_path, monkeypatch, _decl())
    engine = _setup_engine(tmp_path, monkeypatch)

    cfg = load().sources[0]
    with Session(engine) as session:
        src = Source(name="S", url="https://x", gatherer="hikerapi")
        session.add(src)
        session.commit()
        session.refresh(src)
        materialize(session, src, cfg)
        session.commit()

    aid = approvals.create("recurrence_remove", source_name="S", payload={"title": "Weekly Ride"}, reason="no longer")
    assert approvals.approve(aid) is True

    assert load().sources[0].recurrences == []
    with Session(engine) as session:
        event = session.exec(select(Event)).one()
        assert event.archived_at is not None
        assert event.archived_reason == "removed"
#endregion
