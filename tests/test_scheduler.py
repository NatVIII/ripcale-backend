"""Tests for the background ingest scheduler (F11)."""
#region: imports
import threading
from datetime import datetime

import app.services.scheduler as sched
#endregion


def _reset(monkeypatch):
    monkeypatch.setattr(sched, "_thread", None)
    monkeypatch.setattr(sched, "_lock", threading.Lock())
    monkeypatch.setattr(
        sched,
        "_state",
        {"enabled": False, "interval_minutes": None, "last_run_at": None, "next_run_at": None, "running": False},
    )


def test_scheduler_disabled(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ingest_interval_minutes", None)
    _reset(monkeypatch)

    sched.start()

    st = sched.status()
    assert st["enabled"] is False
    assert st["next_run_at"] is None


def test_scheduler_start_sets_state(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ingest_interval_minutes", 60)
    monkeypatch.setattr(settings, "ingest_startup_delay_minutes", 3)
    _reset(monkeypatch)

    sched.start()

    st = sched.status()
    assert st["enabled"] is True
    assert st["interval_minutes"] == 60
    assert st["next_run_at"] is not None
    assert datetime.fromisoformat(st["next_run_at"]) > datetime(2026, 1, 1)


def test_scheduler_start_is_idempotent(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ingest_interval_minutes", 60)
    _reset(monkeypatch)

    sched.start()
    first = sched.status()
    sched.start()  # second call is a no-op
    assert sched.status()["next_run_at"] == first["next_run_at"]


def test_next_run_math():
    now = datetime(2026, 1, 1, 12, 0)
    assert sched._next_run(now, 60) == datetime(2026, 1, 1, 13, 0)
#endregion
