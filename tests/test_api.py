"""Tests for the JSON admin API (F52)."""
#region: imports
import json
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.models import Event, User
#endregion


def _make_client(tmp_path, monkeypatch):
    import app.db as db_mod
    import app.ingest as ingest_mod
    import app.services.actions as actions_mod
    from app.services import auth

    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(actions_mod, "engine", engine)
    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(ingest_mod, "engine", engine)
    monkeypatch.setattr(auth, "engine", engine)

    # create an admin user + API token (the /api/v1/* credential)
    with Session(engine) as session:
        admin = User(username="admin", password_hash=auth.hash_password("hunter2"))
        session.add(admin)
        session.commit()
        session.refresh(admin)
        admin_id = admin.id
    raw_token = auth.create_api_token(admin_id, "test")

    from robyn.testing import TestClient

    from app.admin import app

    return TestClient(app), engine, {"Authorization": f"Bearer {raw_token}"}


def _seed_event(engine, eid, title, categories):
    with Session(engine) as session:
        session.add(Event(id=eid, source_id=1, title=title, categories=categories, start_at=datetime(2030, 1, 1)))
        session.commit()
#endregion


#region: auth
def test_api_missing_token_returns_401(tmp_path, monkeypatch):
    client, _, _ = _make_client(tmp_path, monkeypatch)
    r = client.get("/api/v1/stats")
    assert r.status_code == 401
    assert r.json()["ok"] is False


def test_api_wrong_token_returns_401(tmp_path, monkeypatch):
    client, _, _ = _make_client(tmp_path, monkeypatch)
    r = client.get("/api/v1/stats", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_api_correct_token_returns_200(tmp_path, monkeypatch):
    client, _, auth_header = _make_client(tmp_path, monkeypatch)
    r = client.get("/api/v1/stats", headers=auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "data" in body


def test_api_session_cookie_also_authenticates(tmp_path, monkeypatch):
    from app.services import auth

    client, engine, _ = _make_client(tmp_path, monkeypatch)
    # a session cookie works too (unified auth)
    token = auth.login("admin", "hunter2")
    r = client.get("/api/v1/stats", headers={"Cookie": f"ripcale_session={token}"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
#endregion


#region: envelope + read
def test_api_error_envelope(tmp_path, monkeypatch):
    client, _, auth_header = _make_client(tmp_path, monkeypatch)
    r = client.post("/api/v1/wipe/confirm", headers=auth_header, json_data={})
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert "error" in body


def test_api_events_enumeration(tmp_path, monkeypatch):
    client, engine, auth_header = _make_client(tmp_path, monkeypatch)
    _seed_event(engine, "e1", "Alpha", "intake:art")
    _seed_event(engine, "e2", "Beta", "external:music")

    r = client.get("/api/v1/events", headers=auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    titles = sorted(e["title"] for e in body["data"])
    assert titles == ["Alpha", "Beta"]


def test_api_categories_mapping(tmp_path, monkeypatch):
    from app.config import settings
    from app.intake import IntakeSettings, save as save_intake

    client, engine, auth_header = _make_client(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "intake_file", str(tmp_path / "intake.yaml"))
    save_intake(
        IntakeSettings(
            category_definitions={"external": ["art"]},
            category_symlinks={"intake:raw": "external:art"},
            exposed_classes=["external"],
        )
    )
    _seed_event(engine, "e1", "A", "external:art,intake:raw")

    r = client.get("/api/v1/categories", headers=auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["definitions"] == {"external": ["art"]}
    assert data["symlinks"] == {"intake:raw": "external:art"}
    assert data["exposed_classes"] == ["external"]

    by_name = {c["name"]: c for c in data["categories"]}
    assert by_name["external:art"]["exposed"] is True
    assert by_name["intake:raw"]["exposed"] is False
#endregion


#region: write ops
def test_api_retag_dry_run_vs_commit(tmp_path, monkeypatch):
    client, engine, auth_header = _make_client(tmp_path, monkeypatch)
    _seed_event(engine, "e1", "A", "intake:art")

    # dry-run (default) -> nothing written
    r = client.post("/api/v1/retag", headers=auth_header, json_data={"from": "intake:art", "to": "external:art"})
    assert r.status_code == 200
    assert r.json()["data"]["dry_run"] is True
    assert r.json()["data"]["changed"] == 1
    with Session(engine) as session:
        assert session.get(Event, "e1").categories == "intake:art"

    # commit -> writes
    r = client.post("/api/v1/retag", headers=auth_header, json_data={"from": "intake:art", "to": "external:art", "dry_run": False})
    assert r.status_code == 200
    assert r.json()["data"]["dry_run"] is False
    with Session(engine) as session:
        assert session.get(Event, "e1").categories == "external:art"


def test_api_wipe_challenge_response(tmp_path, monkeypatch):
    client, engine, auth_header = _make_client(tmp_path, monkeypatch)
    _seed_event(engine, "e1", "A", "intake:art")

    # begin -> challenge, no wipe
    r = client.post("/api/v1/wipe/begin", headers=auth_header, json_data={})
    assert r.status_code == 200
    challenge = r.json()["data"]["challenge"]
    with Session(engine) as session:
        assert session.get(Event, "e1") is not None

    # wrong challenge -> error, still not wiped
    r = client.post("/api/v1/wipe/confirm", headers=auth_header, json_data={"challenge": "nope"})
    assert r.status_code == 400
    assert r.json()["ok"] is False
    with Session(engine) as session:
        assert session.get(Event, "e1") is not None

    # correct challenge -> wiped
    r = client.post("/api/v1/wipe/confirm", headers=auth_header, json_data={"challenge": challenge})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    with Session(engine) as session:
        assert session.get(Event, "e1") is None


def test_api_ingest_echoes_dry_run(tmp_path, monkeypatch):
    client, _, auth_header = _make_client(tmp_path, monkeypatch)
    r = client.post("/api/v1/ingest", headers=auth_header, json_data={"dry_run": True})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["dry_run"] is True
    assert data["sources"] == []
#endregion


#region: pipeline stage
def test_api_pipeline_gather(tmp_path, monkeypatch):
    import app.gatherers.elfsight.gatherer as elfsight_gatherer

    fixture = json.loads((Path(__file__).parent / "fixtures" / "elfsight_boot.json").read_text())
    monkeypatch.setattr(elfsight_gatherer, "fetch_json", lambda url: fixture)

    client, _, auth_header = _make_client(tmp_path, monkeypatch)
    r = client.post(
        "/api/v1/pipeline/gather",
        headers=auth_header,
        json_data={"name": "S", "gatherer": "elfsight", "url": "https://x"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["data"]["events"]) == 3
#endregion
