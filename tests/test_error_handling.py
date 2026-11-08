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
    monkeypatch.setattr(ingest_mod, "_write_last_ingest", lambda summaries, archived=None: captured.setdefault("summaries", summaries))

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


def test_ingest_source_issue_is_warning(tmp_path, monkeypatch):
    import app.ingest as ingest_mod
    from app.gatherers.errors import SourceIssue

    engine = create_engine(f"sqlite:///{tmp_path / 'ingest_soft.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ingest_mod, "engine", engine)
    monkeypatch.setattr(ingest_mod, "init_db", lambda: None)
    monkeypatch.setattr("app.services.status.settings.data_dir", str(tmp_path))

    soft = SourceConfig(name="Private", gatherer="broken", url="https://x")
    monkeypatch.setattr(ingest_mod, "load_sources", lambda: [soft])

    captured = {}
    monkeypatch.setattr(ingest_mod, "_write_last_ingest", lambda summaries, archived=None: captured.setdefault("summaries", summaries))

    def soft_run(cfg):
        raise SourceIssue("account private or not found")

    monkeypatch.setattr(ingest_mod, "load_gatherer", lambda name: soft_run)

    ingest_mod.run(dry_run=False)

    summaries = captured["summaries"]
    assert len(summaries) == 1
    assert summaries[0]["status"] == "warning"
    assert "private" in summaries[0]["message"]


def test_ingest_down_and_garbage_severities(tmp_path, monkeypatch):
    import app.ingest as ingest_mod
    from app.gatherers.errors import SourceIssue

    engine = create_engine(f"sqlite:///{tmp_path / 'ingest_sev.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ingest_mod, "engine", engine)
    monkeypatch.setattr(ingest_mod, "init_db", lambda: None)
    monkeypatch.setattr("app.services.status.settings.data_dir", str(tmp_path))

    good = SourceConfig(name="Good", gatherer="elfsight", url="https://x")
    down = SourceConfig(name="Down", gatherer="broken-down", url="https://x")
    garbage = SourceConfig(name="Garbage", gatherer="broken-garbage", url="https://x")
    monkeypatch.setattr(ingest_mod, "load_sources", lambda: [down, garbage, good])

    captured = {}
    monkeypatch.setattr(ingest_mod, "_write_last_ingest", lambda summaries, archived=None: captured.setdefault("summaries", summaries))

    def good_run(cfg):
        return GathererResult(source=cfg, events=[ScrapedEvent(uid="u1", title="Event")])

    def down_run(cfg):
        raise SourceIssue("source unreachable")

    def garbage_run(cfg):
        raise ValueError("unparseable JSON")

    def loader(name):
        return {"elfsight": good_run, "broken-down": down_run, "broken-garbage": garbage_run}[name]

    monkeypatch.setattr(ingest_mod, "load_gatherer", loader)

    ingest_mod.run(dry_run=False)

    summaries = {s["name"]: s for s in captured["summaries"]}
    assert summaries["Good"]["status"] == "ok"
    assert summaries["Down"]["status"] == "warning"
    assert summaries["Garbage"]["status"] == "error"


def test_ingest_scrubs_urls_from_error_messages(tmp_path, monkeypatch):
    import app.ingest as ingest_mod
    from app.services.status import read_status

    engine = create_engine(f"sqlite:///{tmp_path / 'ingest_scrub.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(ingest_mod, "engine", engine)
    monkeypatch.setattr(ingest_mod, "init_db", lambda: None)
    monkeypatch.setattr("app.services.status.settings.data_dir", str(tmp_path))

    bad = SourceConfig(name="Bad", gatherer="broken", url="https://secret.example.com/feed")
    monkeypatch.setattr(ingest_mod, "load_sources", lambda: [bad])

    captured = {}
    monkeypatch.setattr(ingest_mod, "_write_last_ingest", lambda summaries, archived=None: captured.setdefault("summaries", summaries))

    def bad_run(cfg):
        raise RuntimeError("failed to fetch https://secret.example.com/feed")

    monkeypatch.setattr(ingest_mod, "load_gatherer", lambda name: bad_run)

    ingest_mod.run(dry_run=False)

    message = captured["summaries"][0]["message"]
    assert "secret.example.com" not in message
    assert "[redacted-url]" in message

    status = read_status()["Bad"]["message"]
    assert "secret.example.com" not in status
    assert "[redacted-url]" in status


def test_available_gatherers_skips_broken(monkeypatch):
    import app.routers.pipeline as pipeline_mod

    fake = SimpleNamespace(ispkg=True, name="broken")
    monkeypatch.setattr(pipeline_mod.pkgutil, "iter_modules", lambda path: [fake])
    monkeypatch.setattr(pipeline_mod.importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError("nope")))

    assert pipeline_mod._available_gatherers() == []


#region: change-probe enqueue (F21.05)
def _probe_setup(tmp_path):
    from sqlmodel import SQLModel, create_engine, Session

    from app.models import Source

    engine = create_engine(f"sqlite:///{tmp_path / 'probe.db'}")
    SQLModel.metadata.create_all(engine)
    cfg = SourceConfig(name="IG", gatherer="hikerapi", url="https://instagram.com/x")
    session = Session(engine)
    source = Source(
        name="IG", url=cfg.url, gatherer="hikerapi",
        probe_state='{"user_pk": "123", "newest_code": "AAA"}',
    )
    session.add(source)
    session.commit()
    return session, source, cfg


def test_probe_and_enqueue_short_circuits_when_unchanged(tmp_path):
    import app.ingest as ingest_mod

    session, source, cfg = _probe_setup(tmp_path)
    try:
        def run_fn(c):
            raise AssertionError("run_fn must not run on an unchanged probe")

        def probe_fn(c, prev):
            assert prev == {"user_pk": "123", "newest_code": "AAA"}
            return {"changed": False, "state": {"user_pk": "123", "newest_code": "AAA"}}

        summary = ingest_mod._probe_and_enqueue(session, cfg, run_fn, probe_fn, dry_run=False)

        assert summary["skipped_unchanged"] is True
        assert summary["enqueued"] == 0
        session.commit()  # _run_locked commits per source; mimic it before refresh
        session.refresh(source)
        assert source.last_fetched_at is not None
        assert source.probe_state == '{"user_pk": "123", "newest_code": "AAA"}'
    finally:
        session.close()


def test_probe_and_enqueue_runs_when_changed(tmp_path):
    import app.ingest as ingest_mod

    session, source, cfg = _probe_setup(tmp_path)
    try:
        called = {}

        def run_fn(c):
            called["run"] = True
            return GathererResult(source=c, events=[ScrapedEvent(uid="u1", title="Event")])

        def probe_fn(c, prev):
            return {"changed": True, "state": {"user_pk": "123", "newest_code": "BBB"}}

        summary = ingest_mod._probe_and_enqueue(session, cfg, run_fn, probe_fn, dry_run=False)

        assert called.get("run") is True
        assert summary["skipped_unchanged"] is False
        assert summary["enqueued"] == 1
        session.commit()
        session.refresh(source)
        assert source.probe_state == '{"user_pk": "123", "newest_code": "BBB"}'
    finally:
        session.close()
#endregion
