"""Tests for gatherer error handling (F37)."""
#region: imports
from types import SimpleNamespace

from sqlmodel import SQLModel, create_engine

from app.schema import GathererResult, ScrapedEvent, SourceConfig
#endregion


def test_ingest_continues_after_source_failure(tmp_path, monkeypatch):
    import app.ingest as ingest_mod

    engine = create_engine(f"sqlite:///{tmp_path / 'ingest_err.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ingest_mod, "engine", engine)
    monkeypatch.setattr(ingest_mod, "init_db", lambda: None)
    monkeypatch.setattr("app.services.status.settings.data_dir", str(tmp_path))

    good = SourceConfig(name="Good", gatherer="elfsight", url="https://x")
    bad = SourceConfig(name="Bad", gatherer="broken", url="https://x")
    monkeypatch.setattr(ingest_mod, "load_sources", lambda: [bad, good])

    captured = {}
    monkeypatch.setattr(ingest_mod, "_write_last_ingest", lambda summaries: captured.setdefault("summaries", summaries))

    def good_run(cfg):
        return GathererResult(source=cfg, events=[ScrapedEvent(uid="u1", title="Event")])

    def bad_run(cfg):
        raise RuntimeError("boom")

    monkeypatch.setattr(ingest_mod, "load_gatherer", lambda name: good_run if name == "elfsight" else bad_run)

    results = ingest_mod.run(dry_run=False)

    assert len(results) == 1

    summaries = captured["summaries"]
    assert len(summaries) == 2
    error_entry = next(s for s in summaries if s["name"] == "Bad")
    assert error_entry["status"] == "error"
    assert "boom" in error_entry["message"]
    good_entry = next(s for s in summaries if s["name"] == "Good")
    assert good_entry["status"] == "ok"


def test_available_gatherers_skips_broken(monkeypatch):
    import app.routers.pipeline as pipeline_mod

    fake = SimpleNamespace(ispkg=True, name="broken")
    monkeypatch.setattr(pipeline_mod.pkgutil, "iter_modules", lambda path: [fake])
    monkeypatch.setattr(pipeline_mod.importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError("nope")))

    assert pipeline_mod._available_gatherers() == []
