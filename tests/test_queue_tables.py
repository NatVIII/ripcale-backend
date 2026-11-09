"""Tests for the queue tables (F70.04)."""
#region: imports
from sqlmodel import SQLModel, create_engine

from app.models import DedupCandidate
#endregion


def _tables(eng) -> set[str]:
    with eng.connect() as conn:
        return {r[0] for r in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}


def test_queue_dedup_table_is_created(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'queue.db'}")
    SQLModel.metadata.create_all(eng)

    assert "queue_dedup" in _tables(eng)
    assert DedupCandidate.__tablename__ == "queue_dedup"


def test_queue_dedup_has_the_expected_columns(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'queue2.db'}")
    SQLModel.metadata.create_all(eng)

    with eng.connect() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(queue_dedup)")}

    assert {"id", "event_a_id", "event_b_id", "status", "decision", "created_at", "updated_at"} <= cols
