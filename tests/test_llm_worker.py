"""Tests for the LLM worker (app/services/llm_worker.py)."""
#region: imports
import threading

from app.services import llm_worker
#endregion


def _reset():
    w = llm_worker._worker
    w._thread = None
    w._set(enabled=False, running=False, last_tick_at=None, processed=0)


def test_start_does_not_deadlock(monkeypatch):
    # `start()` must not deadlock on its own lock (historic B02: it re-acquired a
    # non-reentrant lock and left the admin app's web server unbound).
    monkeypatch.setattr(llm_worker.settings, "llm_enabled", True)
    monkeypatch.setattr(llm_worker.settings, "deepseek_key", "test-key")
    monkeypatch.setattr(llm_worker._worker, "_loop", lambda: None)  # no-op so the daemon exits

    _reset()

    t = threading.Thread(target=llm_worker.start)
    t.start()
    t.join(timeout=5)
    assert not t.is_alive(), "llm_worker.start() deadlocked on its own lock"

    assert llm_worker._worker._state["enabled"] is True
    assert llm_worker._worker._thread is not None

    _reset()


def test_start_disabled_without_key(monkeypatch):
    monkeypatch.setattr(llm_worker.settings, "llm_enabled", True)
    monkeypatch.setattr(llm_worker.settings, "deepseek_key", "")

    _reset()
    llm_worker.start()

    assert llm_worker._worker._state["enabled"] is False
    assert llm_worker._worker._thread is None

    _reset()
#endregion
