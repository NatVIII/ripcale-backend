"""Tests for the cross-process ingest lock (F11)."""
#region: imports
import os
import time

import app.services.lock as lock
#endregion


def _configure(tmp_path, monkeypatch, interval=60):
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "ingest_interval_minutes", interval)


def test_acquire_release_cycle(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    assert lock.acquire() is True
    assert lock.acquire() is False  # already held
    lock.release()
    assert lock.acquire() is True  # released -> reacquirable
    lock.release()


def test_stale_lock_is_stolen(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, interval=1)  # stale after 60s
    assert lock.acquire() is True

    # backdate the lockfile so it looks like a crashed run
    old = time.time() - 120
    os.utime(lock._lock_path(), (old, old))

    assert lock.acquire() is True  # stale -> stolen + reacquired
    lock.release()


def test_release_is_idempotent(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    lock.release()  # nothing to release -> no error
    assert lock.acquire() is True
    lock.release()
    lock.release()
#endregion
