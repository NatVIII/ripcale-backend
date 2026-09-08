"""Tests for mass retag (F47)."""
#region: imports
from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Event
from app.security import debug_csrf_token
from app.services.retag import _replace_token, retag
#endregion


def _event(engine, eid, title, categories):
    with Session(engine) as session:
        session.add(Event(id=eid, source_id=1, title=title, categories=categories, start_at=datetime(2030, 1, 1)))
        session.commit()


def _categories(engine, eid):
    with Session(engine) as session:
        return session.get(Event, eid).categories
#endregion


#region: _replace_token
def test_replace_token_renames_exact_match():
    assert _replace_token("intake:art,external:music", "intake:art", "external:art") == "external:art,external:music"


def test_replace_token_does_not_partial_match():
    assert _replace_token("intake:art,external:music", "intake:art", "external:art") != "intake:art-exhibition,external:music"
    assert _replace_token("intake:art-exhibition", "intake:art", "external:art") == "intake:art-exhibition"


def test_replace_token_removes_when_to_is_none():
    assert _replace_token("intake:art,external:music", "intake:art", None) == "external:music"
#endregion


#region: retag
def test_retag_renames_across_events(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retag.db'}")
    SQLModel.metadata.create_all(engine)
    _event(engine, "e1", "A", "intake:art,external:music")
    _event(engine, "e2", "B", "intake:art-exhibition")
    _event(engine, "e3", "C", "")

    with Session(engine) as session:
        changed, preview = retag(session, "intake:art", "external:art")
        session.commit()

    assert changed == 1
    assert _categories(engine, "e1") == "external:art,external:music"
    assert _categories(engine, "e2") == "intake:art-exhibition"  # untouched (no partial match)
    assert _categories(engine, "e3") == ""
    assert preview == [("A", "intake:art,external:music", "external:art,external:music")]


def test_retag_removes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'remove.db'}")
    SQLModel.metadata.create_all(engine)
    _event(engine, "e1", "A", "intake:art,external:music")

    with Session(engine) as session:
        changed, _ = retag(session, "intake:art", None)
        session.commit()

    assert changed == 1
    assert _categories(engine, "e1") == "external:music"
#endregion


#region: route
def test_retag_route_dry_run_vs_commit(tmp_path, monkeypatch):
    import app.routers.retag as retag_router_mod

    engine = create_engine(f"sqlite:///{tmp_path / 'route.db'}")
    SQLModel.metadata.create_all(engine)
    _event(engine, "e1", "A", "intake:art")

    monkeypatch.setattr(retag_router_mod, "engine", engine)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)

    r = client.get("/debug/retag")
    assert r.status_code == 200
    assert "dry-run" in r.text

    # dry-run -> preview + nothing written
    r = client.post("/debug/retag", form_data={"csrf_token": debug_csrf_token(), "from": "intake:art", "to": "external:art", "dry_run": "1"})
    assert r.status_code == 200
    assert "dry run" in r.text
    assert _categories(engine, "e1") == "intake:art"

    # commit -> writes
    r = client.post("/debug/retag", form_data={"csrf_token": debug_csrf_token(), "from": "intake:art", "to": "external:art"})
    assert r.status_code == 200
    assert "committed" in r.text
    assert _categories(engine, "e1") == "external:art"


def test_retag_route_requires_csrf(tmp_path, monkeypatch):
    import app.routers.retag as retag_router_mod

    engine = create_engine(f"sqlite:///{tmp_path / 'csrf.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(retag_router_mod, "engine", engine)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)
    r = client.post("/debug/retag", form_data={"from": "intake:art", "to": "external:art"})
    assert r.status_code == 403
#endregion
