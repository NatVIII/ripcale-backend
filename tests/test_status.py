"""Tests for the per-source run status store (F37.01)."""
#region: imports
from sqlmodel import SQLModel, create_engine

from app.schema import GathererResult, ScrapedEvent, SourceConfig
from app.services import status
#endregion


def test_record_and_read_status(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.status.settings.data_dir", str(tmp_path))

    assert status.read_status() == {}

    status.record_status("A", "ok", events=5)
    statuses = status.read_status()
    assert statuses["A"]["status"] == "ok"
    assert statuses["A"]["events"] == 5
    assert "at" in statuses["A"]

    # upsert doesn't clobber other sources
    status.record_status("B", "error", message="boom")
    statuses = status.read_status()
    assert set(statuses) == {"A", "B"}
    assert statuses["B"]["message"] == "boom"


def test_record_run_warning_on_zero_events(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.status.settings.data_dir", str(tmp_path))

    status.record_run("A", 0)
    assert status.read_status()["A"]["status"] == "warning"
    assert status.read_status()["A"]["message"] == "returned 0 events"

    status.record_run("A", 10)
    assert status.read_status()["A"]["status"] == "ok"


def test_source_status_defaults_to_never():
    assert status.source_status({}, "missing") == "never"
    assert status.source_status({"x": {"status": "error"}}, "x") == "error"


def test_gatherer_rollup_highest_severity():
    sources = [
        {"name": "a", "gatherer": "elfsight"},
        {"name": "b", "gatherer": "elfsight"},
        {"name": "c", "gatherer": "other"},
    ]
    statuses = {"a": {"status": "ok"}, "b": {"status": "error"}, "c": {"status": "warning"}}

    rollup = status.gatherer_rollup(sources, statuses)
    assert rollup["elfsight"] == "error"  # error dominates ok
    assert rollup["other"] == "warning"

    # never only when every source is never
    assert status.gatherer_rollup(sources, {}) == {"elfsight": "never", "other": "never"}


def test_ingest_records_status(tmp_path, monkeypatch):
    import app.ingest as ingest_mod

    engine = create_engine(f"sqlite:///{tmp_path / 'status.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ingest_mod, "engine", engine)
    monkeypatch.setattr(ingest_mod, "init_db", lambda: None)
    monkeypatch.setattr("app.services.status.settings.data_dir", str(tmp_path))

    good = SourceConfig(name="Good", gatherer="elfsight", url="https://x")
    monkeypatch.setattr(ingest_mod, "load_sources", lambda: [good])
    monkeypatch.setattr(
        ingest_mod,
        "load_gatherer",
        lambda name: (lambda cfg: GathererResult(source=cfg, events=[ScrapedEvent(uid="u1", title="Event")])),
    )

    ingest_mod.run(dry_run=False)

    assert status.read_status()["Good"]["status"] == "ok"
    assert status.read_status()["Good"]["events"] == 1
