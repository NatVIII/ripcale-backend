"""Tests for the JSON admin API (F52)."""
#region: imports
import json
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.models import Event
#endregion


TOKEN = "test-api-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _make_client(tmp_path, monkeypatch, token):
    from app.config import settings

    monkeypatch.setattr(settings, "api_token", token)

    import app.db as db_mod
    import app.ingest as ingest_mod
    import app.routers.api as api_router_mod

    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(api_router_mod, "engine", engine)
    monkeypatch.setattr(db_mod, "engine", engine)
    monkeypatch.setattr(ingest_mod, "engine", engine)

    from robyn.testing import TestClient

    from app.admin import app

    return TestClient(app), engine


def _seed_event(engine, eid, title, categories):
    with Session(engine) as session:
        session.add(Event(id=eid, source_id=1, title=title, categories=categories, start_at=datetime(2030, 1, 1)))
        session.commit()
#endregion


#region: auth
def test_api_unconfigured_returns_503(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch, "")
    r = client.get("/api/v1/stats")
    assert r.status_code == 503
    assert r.json()["ok"] is False


def test_api_missing_token_returns_401(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch, TOKEN)
    r = client.get("/api/v1/stats")
    assert r.status_code == 401
    assert r.json()["ok"] is False


def test_api_wrong_token_returns_401(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch, TOKEN)
    r = client.get("/api/v1/stats", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_api_correct_token_returns_200(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch, TOKEN)
    r = client.get("/api/v1/stats", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "data" in body
#endregion


#region: envelope + read
def test_api_error_envelope(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch, TOKEN)
    r = client.post("/api/v1/wipe/confirm", headers=AUTH, json_data={})
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert "error" in body


def test_api_events_enumeration(tmp_path, monkeypatch):
    client, engine = _make_client(tmp_path, monkeypatch, TOKEN)
    _seed_event(engine, "e1", "Alpha", "intake:art")
    _seed_event(engine, "e2", "Beta", "external:music")

    r = client.get("/api/v1/events", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    titles = sorted(e["title"] for e in body["data"])
    assert titles == ["Alpha", "Beta"]
#endregion


#region: write ops
def test_api_retag_dry_run_vs_commit(tmp_path, monkeypatch):
    client, engine = _make_client(tmp_path, monkeypatch, TOKEN)
    _seed_event(engine, "e1", "A", "intake:art")

    # dry-run (default) -> nothing written
    r = client.post("/api/v1/retag", headers=AUTH, json_data={"from": "intake:art", "to": "external:art"})
    assert r.status_code == 200
    assert r.json()["data"]["dry_run"] is True
    assert r.json()["data"]["changed"] == 1
    with Session(engine) as session:
        assert session.get(Event, "e1").categories == "intake:art"

    # commit -> writes
    r = client.post("/api/v1/retag", headers=AUTH, json_data={"from": "intake:art", "to": "external:art", "dry_run": False})
    assert r.status_code == 200
    assert r.json()["data"]["dry_run"] is False
    with Session(engine) as session:
        assert session.get(Event, "e1").categories == "external:art"


def test_api_wipe_challenge_response(tmp_path, monkeypatch):
    client, engine = _make_client(tmp_path, monkeypatch, TOKEN)
    _seed_event(engine, "e1", "A", "intake:art")

    # begin -> challenge, no wipe
    r = client.post("/api/v1/wipe/begin", headers=AUTH, json_data={})
    assert r.status_code == 200
    challenge = r.json()["data"]["challenge"]
    with Session(engine) as session:
        assert session.get(Event, "e1") is not None

    # wrong challenge -> error, still not wiped
    r = client.post("/api/v1/wipe/confirm", headers=AUTH, json_data={"challenge": "nope"})
    assert r.status_code == 400
    assert r.json()["ok"] is False
    with Session(engine) as session:
        assert session.get(Event, "e1") is not None

    # correct challenge -> wiped
    r = client.post("/api/v1/wipe/confirm", headers=AUTH, json_data={"challenge": challenge})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    with Session(engine) as session:
        assert session.get(Event, "e1") is None


def test_api_ingest_echoes_dry_run(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch, TOKEN)
    r = client.post("/api/v1/ingest", headers=AUTH, json_data={"dry_run": True})
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

    client, _ = _make_client(tmp_path, monkeypatch, TOKEN)
    r = client.post(
        "/api/v1/pipeline/gather",
        headers=AUTH,
        json_data={"name": "S", "gatherer": "elfsight", "url": "https://x"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["data"]["events"]) == 3
#endregion
