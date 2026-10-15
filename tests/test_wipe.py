"""Tests for the challenge-response database wipe (F37.03 / F53)."""
#region: imports
from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine, select

from app.db import wipe_db
from app.models import Event, PendingPost, Source
from app.security import debug_csrf_token
from app.services.status import read_status, record_status
from app.services.wipe import wipe_all
#endregion


#region: helpers
def _seed(engine, events: int = 2) -> None:
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        for i in range(events):
            session.add(
                Event(
                    id=f"e{i}",
                    source_id=src.id,
                    title=f"Event {i}",
                    start_at=datetime(2030, 1, 1 + i, 0, 0),
                )
            )
        session.commit()


def _counts(engine):
    with Session(engine) as session:
        return len(session.exec(select(Event)).all()), len(session.exec(select(Source)).all())
#endregion


#region: wipe_db
def test_wipe_db_empties_tables_and_schema_survives(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'wipe.db'}")
    SQLModel.metadata.create_all(engine)
    _seed(engine)

    monkeypatch.setattr("app.db.engine", engine)
    assert wipe_db() == (2, 1)

    with Session(engine) as session:
        assert session.exec(select(Event)).all() == []
        assert session.exec(select(Source)).all() == []

    # schema still valid — a new source can be inserted
    with Session(engine) as session:
        session.add(Source(name="S2", url="https://y"))
        session.commit()
    assert _counts(engine) == (0, 1)


def test_wipe_db_clears_pending_posts_before_sources(tmp_path, monkeypatch):
    """Wipe must not trip the source.id FK from pending posts (B03)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'wipe_pending.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(PendingPost(uid="p1", source_id=src.id, caption="ride"))
        session.commit()

    monkeypatch.setattr("app.db.engine", engine)
    assert wipe_db() == (0, 1)

    with Session(engine) as session:
        assert session.exec(select(Source)).all() == []
        assert session.exec(select(PendingPost)).all() == []
#endregion


def test_wipe_preserves_api_tokens_and_clears_sessions(tmp_path, monkeypatch):
    """Wipe resets events but must NOT break API connectivity (tokens survive)."""
    from app.models import ApiToken, LoginSession, User

    engine = create_engine(f"sqlite:///{tmp_path / 'wipe_auth.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(username="admin", password_hash="x")
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id
        session.add(LoginSession(token="sess1", user_id=user_id, expires_at=datetime(2030, 1, 1)))
        session.add(ApiToken(token_hash="hash1", user_id=user_id, label="t"))
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(Event(id="e1", source_id=src.id, title="Event"))
        session.add(PendingPost(uid="p1", source_id=src.id, caption="ride"))
        session.commit()

    monkeypatch.setattr("app.db.engine", engine)
    assert wipe_db() == (1, 1)

    with Session(engine) as session:
        assert session.exec(select(Event)).all() == []
        assert session.exec(select(Source)).all() == []
        assert session.exec(select(PendingPost)).all() == []
        assert session.get(User, user_id) is not None          # credentials preserved
        assert session.get(ApiToken, "hash1") is not None      # API token preserved
        assert session.get(LoginSession, "sess1") is None      # session cleared
#endregion


#region: wipe_all
def test_wipe_all_resets_status_and_last_ingest(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'wipeall.db'}")
    SQLModel.metadata.create_all(engine)
    _seed(engine, events=1)

    monkeypatch.setattr("app.db.engine", engine)
    record_status("S", "ok", events=1)
    (tmp_path / "last_ingest.json").write_text("{}")

    assert wipe_all() == {"events": 1, "sources": 1}
    assert read_status() == {}
    assert not (tmp_path / "last_ingest.json").exists()
#endregion


#region: route
def test_wipe_route_challenge_response(tmp_path, monkeypatch):
    from app.services import actions

    engine = create_engine(f"sqlite:///{tmp_path / 'route.db'}")
    SQLModel.metadata.create_all(engine)
    _seed(engine)

    monkeypatch.setattr("app.db.engine", engine)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)

    # begin page renders
    r = client.get("/debug/wipe")
    assert r.status_code == 200
    assert "delete database" in r.text

    # begin -> reveals the challenge + confirm button, DB untouched
    r = client.post("/debug/wipe", form_data={"csrf_token": debug_csrf_token(), "stage": "begin"})
    assert r.status_code == 200
    assert "confirm wipe" in r.text
    assert _counts(engine) == (2, 1)

    # wrong challenge -> error, nothing deleted
    r = client.post("/debug/wipe", form_data={"csrf_token": debug_csrf_token(), "stage": "confirm", "challenge": "nope"})
    assert r.status_code == 200
    assert "nothing was deleted" in r.text
    assert _counts(engine) == (2, 1)

    # correct challenge -> wiped
    challenge = actions.wipe_begin()
    r = client.post("/debug/wipe", form_data={"csrf_token": debug_csrf_token(), "stage": "confirm", "challenge": challenge})
    assert r.status_code == 200
    assert "database wiped" in r.text
    assert _counts(engine) == (0, 0)


def test_wipe_route_requires_csrf(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'csrf.db'}")
    SQLModel.metadata.create_all(engine)
    _seed(engine)
    monkeypatch.setattr("app.db.engine", engine)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)
    r = client.post("/debug/wipe", form_data={"stage": "begin"})
    assert r.status_code == 403
    assert _counts(engine) == (2, 1)
#endregion


#region: resume
def test_wipe_does_not_stop_server_and_can_resume(tmp_path, monkeypatch, session_headers):
    import app.routers.events as events_router_mod

    engine = create_engine(f"sqlite:///{tmp_path / 'resume.db'}")
    SQLModel.metadata.create_all(engine)
    _seed(engine, events=2)

    monkeypatch.setattr("app.services.actions.engine", engine)
    monkeypatch.setattr("app.db.engine", engine)
    monkeypatch.setattr(events_router_mod, "engine", engine)

    from robyn.testing import TestClient

    from app.admin import app as admin_app
    from app.public import app as public_app

    admin_client = TestClient(admin_app)
    public_client = TestClient(public_app)

    # wipe directly (route-level verification covered elsewhere)
    assert wipe_all() == {"events": 2, "sources": 1}

    # server still running: admin dashboard + public read API both respond
    assert admin_client.get("/debug", headers=session_headers).status_code == 200
    r = public_client.get("/events")
    assert r.status_code == 200
    assert r.json() == []

    # can resume: re-ingest repopulates the wiped DB
    import app.ingest as ingest_mod
    from app.schema import GathererResult, ScrapedEvent, SourceConfig

    monkeypatch.setattr(ingest_mod, "engine", engine)
    monkeypatch.setattr(ingest_mod, "init_db", lambda: None)
    cfg = SourceConfig(name="Studio Two Three", gatherer="elfsight", url="https://x")
    monkeypatch.setattr(ingest_mod, "load_sources", lambda: [cfg])
    monkeypatch.setattr(
        ingest_mod,
        "load_gatherer",
        lambda name: (lambda c: GathererResult(source=c, events=[ScrapedEvent(uid="u1", title="Fresh")])),
    )
    ingest_mod.run(dry_run=False)

    assert _counts(engine) == (1, 1)
    r = public_client.get("/events")
    assert [e["title"] for e in r.json()] == ["Fresh"]
#endregion
