"""Tests for the declarative migrations (F70.01)."""
#region: imports
from sqlmodel import create_engine

import app.db as db
#endregion


def _old_schema(tmp_path):
    """An 'old' DB: the tables exist but are missing post-initial columns."""
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE event (id VARCHAR PRIMARY KEY)")
        conn.exec_driver_sql("CREATE TABLE source (id INTEGER PRIMARY KEY)")
        conn.exec_driver_sql("CREATE TABLE pendingpost (uid VARCHAR PRIMARY KEY)")
    return eng


def test_declarative_migration_backfills_old_schema(tmp_path, monkeypatch):
    eng = _old_schema(tmp_path)
    monkeypatch.setattr(db, "engine", eng)

    db._migrate()

    with eng.connect() as conn:
        event_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(event)")}
        source_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(source)")}
        pending_cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(pendingpost)")}

    assert {"archived_at", "archived_reason", "pinned", "placeholder"} <= event_cols
    assert {"llm_context", "probe_state"} <= source_cols
    assert "published_at" in pending_cols


def test_migration_is_idempotent(tmp_path, monkeypatch):
    eng = _old_schema(tmp_path)
    monkeypatch.setattr(db, "engine", eng)

    db._migrate()
    db._migrate()  # second run must not raise

    with eng.connect() as conn:
        event_cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(event)")]
        indexes = {r[1] for r in conn.exec_driver_sql("PRAGMA index_list(event)")}

    assert event_cols.count("archived_at") == 1
    assert "ix_event_archived_at" in indexes
