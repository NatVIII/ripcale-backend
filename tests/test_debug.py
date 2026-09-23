"""Tests for debug tooling: IP allowlist, CSRF, stats, and /debug routes."""
#region: imports
from datetime import datetime
from types import SimpleNamespace

from sqlmodel import Session, SQLModel, create_engine

from app.models import Event, Source
from app.security import debug_csrf_token, in_docker, is_debug_allowed, verify_csrf
from app.services import stats
#endregion


#region: security
def test_is_debug_allowed_loopback(monkeypatch):
    monkeypatch.setattr("app.security.settings.debug_allowed_cidrs", "")
    assert is_debug_allowed("127.0.0.1") is True
    assert is_debug_allowed("::1") is True


def test_is_debug_allowed_cidr(monkeypatch):
    monkeypatch.setattr("app.security.settings.debug_allowed_cidrs", "10.0.0.0/8")
    assert is_debug_allowed("10.1.2.3") is True
    assert is_debug_allowed("8.8.8.8") is False


def test_is_debug_allowed_invalid_cidr(monkeypatch):
    monkeypatch.setattr("app.security.settings.debug_allowed_cidrs", "not-a-cidr")
    assert is_debug_allowed("1.2.3.4") is False
    assert is_debug_allowed("127.0.0.1") is True


def test_is_debug_allowed_docker(monkeypatch):
    monkeypatch.setattr("app.security.settings.debug_allowed_cidrs", "")
    monkeypatch.setattr("app.security.in_docker", lambda: True)
    assert is_debug_allowed("172.18.0.1") is True
    assert is_debug_allowed("172.31.255.254") is True
    assert is_debug_allowed("8.8.8.8") is False
    assert is_debug_allowed("127.0.0.1") is True


def test_in_docker_detection(monkeypatch):
    monkeypatch.delenv("RIPCALE_IN_DOCKER", raising=False)
    monkeypatch.setattr("app.security.os.path.exists", lambda p: p == "/.dockerenv")
    assert in_docker() is True

    monkeypatch.setattr("app.security.os.path.exists", lambda p: False)
    assert in_docker() is False

    monkeypatch.setenv("RIPCALE_IN_DOCKER", "1")
    assert in_docker() is True


def test_verify_csrf():
    token = debug_csrf_token()
    ok = SimpleNamespace(form_data={"csrf_token": token})
    bad = SimpleNamespace(form_data={"csrf_token": "wrong"})
    missing = SimpleNamespace(form_data={})
    assert verify_csrf(ok) is True
    assert verify_csrf(bad) is False
    assert verify_csrf(missing) is False
#endregion


#region: stats
def _seeded(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'debug.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        src = Source(name="S", url="https://x", gatherer="elfsight")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(
            Event(
                id="e1", source_id=src.id, title="Upcoming",
                start_at=datetime(2030, 1, 1, 0, 0), categories="art,music",
            )
        )
        session.add(
            Event(
                id="e2", source_id=src.id, title="Past",
                start_at=datetime(2020, 1, 1, 0, 0), categories="art",
            )
        )
        session.commit()
        src_id = src.id
    return engine, src_id


def test_stats_overview_and_sources(tmp_path):
    engine, src_id = _seeded(tmp_path)
    with Session(engine) as session:
        ov = stats.overview(session)
        assert ov["events"] == 2
        assert ov["sources"] == 1
        assert ov["upcoming"] == 1
        assert ov["past"] == 1
        assert {"name": "art", "count": 2} in ov["categories"]

        srcs = stats.sources(session)
        assert srcs[0]["name"] == "S"
        assert srcs[0]["event_count"] == 2


def test_stats_event_dump(tmp_path):
    engine, src_id = _seeded(tmp_path)
    with Session(engine) as session:
        dump = stats.event_dump(session, "e1")
        assert dump["title"] == "Upcoming"
        assert dump["source"] == "S"
        assert stats.event_dump(session, "nope") is None


def test_overview_archived_and_sources_exclude_archived(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'arch.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(Event(id="live", source_id=src.id, title="Live", start_at=datetime(2030, 1, 1)))
        session.add(
            Event(id="dead", source_id=src.id, title="Dead", start_at=datetime(2030, 1, 2), archived_at=datetime(2026, 1, 1))
        )
        session.commit()

    with Session(engine) as session:
        ov = stats.overview(session)
        assert ov["archived"] == 1
        assert ov["events"] == 1
        srcs = stats.sources(session)
        assert srcs[0]["event_count"] == 1
#endregion


#region: routes
def test_debug_and_pipeline_routes(tmp_path, monkeypatch, session_headers):
    import app.routers.debug as debug_router_mod
    import app.routers.pipeline as pipeline_router_mod
    import app.gatherers.elfsight.gatherer as elfsight_gatherer

    engine = create_engine(f"sqlite:///{tmp_path / 'routes.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(Event(id="e1", source_id=src.id, title="Upcoming", start_at=datetime(2030, 1, 1, 0, 0), categories="art"))
        session.commit()

    monkeypatch.setattr("app.services.actions.engine", engine)
    monkeypatch.setattr(elfsight_gatherer, "fetch_json", lambda url: {
        "data": {"widgets": {"w": {"data": {"settings": {"eventTypes": [], "locations": [], "events": []}}}}}
    })

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)

    # dashboard renders
    r = client.get("/debug", headers=session_headers)
    assert r.status_code == 200
    assert "Upcoming" not in r.text or "events: 1" in r.text

    # JSON stats
    assert client.get("/debug/stats").json()["events"] == 1
    assert client.get("/debug/sources").json()[0]["name"] == "S"
    assert client.get("/debug/events/e1").json()["title"] == "Upcoming"
    assert client.get("/debug/events/nope").status_code == 404

    # pipeline pages render
    assert client.get("/debug/pipeline").status_code == 200
    assert client.get("/debug/pipeline/gather").status_code == 200

    # pipeline POST: missing/incorrect CSRF -> 403
    r = client.post("/debug/pipeline/gather", form_data={"source": "manual", "gatherer": "elfsight", "url": "https://x"})
    assert r.status_code == 403

    # pipeline POST: correct CSRF -> 200, runs the gatherer
    r = client.post(
        "/debug/pipeline/gather",
        form_data={"csrf_token": debug_csrf_token(), "source": "manual", "gatherer": "elfsight", "name": "x", "url": "https://x"},
    )
    assert r.status_code == 200


def test_debug_event_page_and_pin(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'event.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(Event(id="e1", source_id=src.id, title="Upcoming", start_at=datetime(2030, 1, 1, 0, 0)))
        session.commit()

    monkeypatch.setattr("app.services.actions.engine", engine)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)

    r = client.get("/debug/event/e1")
    assert r.status_code == 200
    assert "Upcoming" in r.text
    assert "pin" in r.text

    r = client.post("/debug/event/e1/pin", form_data={"csrf_token": debug_csrf_token(), "pinned": "1"})
    assert r.status_code == 200
    with Session(engine) as session:
        assert session.get(Event, "e1").pinned is True


def test_debug_event_page_shows_all_fields_and_images(tmp_path, monkeypatch):
    from app.schema import ImageRef, dump_images

    engine = create_engine(f"sqlite:///{tmp_path / 'eventfull.db'}")
    SQLModel.metadata.create_all(engine)
    fn = "a" * 64 + ".jpg"
    (tmp_path / "images").mkdir(parents=True, exist_ok=True)
    (tmp_path / "images" / fn).write_bytes(b"x")
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(
            Event(
                id="e1", source_id=src.id, title="Upcoming", uid="u1",
                description="desc", location="loc", url="https://e.example",
                timezone="America/New_York", rrule="FREQ=WEEKLY",
                start_at=datetime(2030, 1, 1, 0, 0),
                images=dump_images([ImageRef(url=f"/images/{fn}", alt="cover", source_url="https://cdn/x.jpg")]),
            )
        )
        session.commit()

    monkeypatch.setattr("app.services.actions.engine", engine)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)

    r = client.get("/debug/event/e1")
    assert r.status_code == 200
    assert "u1" in r.text            # uid (previously hidden)
    assert "desc" in r.text          # description
    assert "loc" in r.text           # location
    assert "FREQ=WEEKLY" in r.text   # rrule
    assert "America/New_York" in r.text  # timezone
    assert "<img" in r.text          # image preview
    assert "hosted" in r.text        # kept-on-server marker
    assert "cover" in r.text         # alt text


def test_debug_images_page_and_prune(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'images.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("app.services.actions.engine", engine)

    fn = "e" * 64 + ".jpg"
    (tmp_path / "images").mkdir(parents=True, exist_ok=True)
    (tmp_path / "images" / fn).write_bytes(b"orphan")

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)

    r = client.get("/debug/images")
    assert r.status_code == 200
    assert fn in r.text

    r = client.post("/debug/images", form_data={"csrf_token": debug_csrf_token(), "dry_run": "1"})
    assert r.status_code == 200
    assert (tmp_path / "images" / fn).exists()  # dry-run

    r = client.post("/debug/images", form_data={"csrf_token": debug_csrf_token()})
    assert r.status_code == 200
    assert not (tmp_path / "images" / fn).exists()  # committed


def test_debug_event_edit_page_and_post(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'edit.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(Event(id="e1", source_id=src.id, title="Upcoming", start_at=datetime(2030, 1, 1, 0, 0)))
        session.commit()

    monkeypatch.setattr("app.services.actions.engine", engine)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)

    r = client.get("/debug/event/e1/edit")
    assert r.status_code == 200
    assert "Upcoming" in r.text

    r = client.post(
        "/debug/event/e1/edit",
        form_data={"csrf_token": debug_csrf_token(), "title": "Changed", "start_at": "2030-01-01T00:00:00", "pinned": "1"},
    )
    assert r.status_code == 200
    with Session(engine) as session:
        assert session.get(Event, "e1").title == "Changed"


def test_debug_events_page_renders(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'events.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(Event(id="e1", source_id=src.id, title="Upcoming", start_at=datetime(2030, 1, 1, 0, 0)))
        session.commit()

    monkeypatch.setattr("app.services.actions.engine", engine)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)
    r = client.get("/debug/events")
    assert r.status_code == 200
    assert "Upcoming" in r.text
    assert "/debug/event/e1" in r.text
    assert "America/New_York" in r.text


def test_debug_shows_scheduler_line(tmp_path, monkeypatch, session_headers):
    engine = create_engine(f"sqlite:///{tmp_path / 'sched.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("app.services.actions.engine", engine)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)
    r = client.get("/debug", headers=session_headers)
    assert r.status_code == 200
    assert "ingest scheduler" in r.text
#endregion
