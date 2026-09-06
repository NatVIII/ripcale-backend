"""Tests for the debug ingest trigger (F37.04)."""
#region: imports
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Event, Source
from app.schema import GathererResult, ScrapedEvent, SourceConfig
from app.security import debug_csrf_token
#endregion


#region: helpers
def _setup_ingest(tmp_path, monkeypatch, source: SourceConfig | None = None, run_fn=None):
    import app.ingest as ingest_mod

    engine = create_engine(f"sqlite:///{tmp_path / 'ingest_route.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ingest_mod, "engine", engine)
    monkeypatch.setattr(ingest_mod, "init_db", lambda: None)
    if source is not None:
        monkeypatch.setattr(ingest_mod, "load_sources", lambda: [source])
    if run_fn is not None:
        monkeypatch.setattr(ingest_mod, "load_gatherer", lambda name: run_fn)
    return ingest_mod, engine


def _one_event_run():
    return lambda cfg: GathererResult(source=cfg, events=[ScrapedEvent(uid="u1", title="Event")])
#endregion


#region: shared core
def test_run_and_run_report_share_core(monkeypatch):
    import app.ingest as ingest_mod

    calls = []
    monkeypatch.setattr(ingest_mod, "_run", lambda dry_run: calls.append(dry_run) or ([], []))

    ingest_mod.run(dry_run=True)
    ingest_mod.run_report(dry_run=False)

    assert calls == [True, False]


def test_run_report_returns_summaries(tmp_path, monkeypatch):
    ingest_mod, engine = _setup_ingest(
        tmp_path, monkeypatch, SourceConfig(name="S", gatherer="elfsight", url="https://x"), _one_event_run()
    )

    summaries = ingest_mod.run_report(dry_run=True)

    assert summaries[0]["name"] == "S"
    assert summaries[0]["status"] == "ok"
    assert summaries[0]["new"] == 1
    assert summaries[0]["inserted"] is None  # dry run writes nothing
    with Session(engine) as session:
        assert session.exec(select(Event)).all() == []
        assert session.exec(select(Source)).all() == []
    assert not (tmp_path / "last_ingest.json").exists()


def test_run_report_commit_writes_and_persists(tmp_path, monkeypatch):
    ingest_mod, engine = _setup_ingest(
        tmp_path, monkeypatch, SourceConfig(name="S", gatherer="elfsight", url="https://x"), _one_event_run()
    )

    summaries = ingest_mod.run_report(dry_run=False)

    assert summaries[0]["inserted"] == 1
    with Session(engine) as session:
        assert len(session.exec(select(Event)).all()) == 1
        assert len(session.exec(select(Source)).all()) == 1
    assert (tmp_path / "last_ingest.json").exists()
#endregion


#region: route
def test_ingest_route_dry_run_vs_commit(tmp_path, monkeypatch):
    _setup_ingest(
        tmp_path, monkeypatch, SourceConfig(name="S", gatherer="elfsight", url="https://x"), _one_event_run()
    )
    import app.ingest as ingest_mod

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)

    # GET renders the form
    r = client.get("/debug/ingest")
    assert r.status_code == 200
    assert "run ingest" in r.text

    # dry-run (checkbox checked) -> nothing written
    r = client.post("/debug/ingest", form_data={"csrf_token": debug_csrf_token(), "dry_run": "1"})
    assert r.status_code == 200
    assert "nothing written" in r.text
    with Session(ingest_mod.engine) as session:
        assert session.exec(select(Event)).all() == []

    # commit (no dry_run field) -> writes
    r = client.post("/debug/ingest", form_data={"csrf_token": debug_csrf_token()})
    assert r.status_code == 200
    assert "committed" in r.text
    with Session(ingest_mod.engine) as session:
        assert len(session.exec(select(Event)).all()) == 1


def test_ingest_route_error_source_shows_error(tmp_path, monkeypatch):
    def boom(cfg):
        raise RuntimeError("boom")

    _setup_ingest(tmp_path, monkeypatch, SourceConfig(name="Bad", gatherer="broken", url="https://x"), boom)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)
    r = client.post("/debug/ingest", form_data={"csrf_token": debug_csrf_token(), "dry_run": "1"})
    assert r.status_code == 200
    assert "boom" in r.text
    assert "🔴" in r.text


def test_ingest_route_requires_csrf(tmp_path, monkeypatch):
    _setup_ingest(tmp_path, monkeypatch)

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)
    r = client.post("/debug/ingest", form_data={"dry_run": "1"})
    assert r.status_code == 403
#endregion
