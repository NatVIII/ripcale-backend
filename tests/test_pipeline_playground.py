"""Tests for the pipeline playground decide dry-run/commit toggle."""
#region: imports
import json
from pathlib import Path

import app.gatherers.elfsight.gatherer as elfsight_gatherer
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Event
from app.security import debug_csrf_token
#endregion


FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "elfsight_boot.json").read_text())
WIDGET_URL = "https://fake/boot/?w=24ddbed9-c732-4102-abd2-02990fae125b"


def test_decide_dry_run_vs_commit(tmp_path, monkeypatch):
    import app.routers.pipeline as pipeline_router_mod

    engine = create_engine(f"sqlite:///{tmp_path / 'decide.db'}")
    SQLModel.metadata.create_all(engine)

    monkeypatch.setattr("app.services.actions.engine", engine)
    monkeypatch.setattr(elfsight_gatherer, "fetch_json", lambda url: FIXTURE)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)
    form = {
        "csrf_token": debug_csrf_token(),
        "source": "manual",
        "gatherer": "elfsight",
        "name": "Studio Two Three",
        "url": WIDGET_URL,
    }

    # dry-run (checkbox checked) -> nothing written
    r = client.post("/debug/pipeline/decide", form_data={**form, "dry_run": "1"})
    assert r.status_code == 200
    assert "nothing written" in r.text
    with Session(engine) as session:
        assert len(session.exec(select(Event)).all()) == 0

    # commit (checkbox unchecked -> no dry_run field) -> writes
    r = client.post("/debug/pipeline/decide", form_data=form)
    assert r.status_code == 200
    assert "committed" in r.text
    with Session(engine) as session:
        assert len(session.exec(select(Event)).all()) == 3


def test_categorize_dry_run_vs_commit(tmp_path, monkeypatch):
    import app.routers.pipeline as pipeline_router_mod

    engine = create_engine(f"sqlite:///{tmp_path / 'categorize.db'}")
    SQLModel.metadata.create_all(engine)

    monkeypatch.setattr("app.services.actions.engine", engine)
    monkeypatch.setattr(elfsight_gatherer, "fetch_json", lambda url: FIXTURE)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)

    # GET renders the form
    assert "include configured rules" in client.get("/debug/pipeline/categorize").text

    form = {
        "csrf_token": debug_csrf_token(),
        "source": "manual",
        "gatherer": "elfsight",
        "name": "Studio Two Three",
        "url": WIDGET_URL,
        "mode": "regex",
        "fields": "title",
        "regex": "(?i)screening",
        "categories": "film",
    }

    # dry-run -> shows resulting categories, writes nothing
    r = client.post("/debug/pipeline/categorize", form_data={**form, "dry_run": "1"})
    assert r.status_code == 200
    assert "resulting categories" in r.text
    assert "intake:film" in r.text
    with Session(engine) as session:
        assert len(session.exec(select(Event)).all()) == 0

    # commit (no dry_run) -> writes
    r = client.post("/debug/pipeline/categorize", form_data=form)
    assert r.status_code == 200
    assert "committed" in r.text
    with Session(engine) as session:
        assert len(session.exec(select(Event)).all()) == 3
