"""Background ingest scheduler (F11).

A daemon thread that runs the full ingest on a configurable interval, after a
startup cooldown. Only the admin app starts it. State (enabled / interval /
last+next run) is module-level so the admin UI and API can read it.
"""
#region: imports
import logging
import threading
import time
from datetime import timedelta

from app.config import settings
from app.models import utcnow
#endregion


logger = logging.getLogger(__name__)


#region: state
_state = {
    "enabled": False,
    "interval_minutes": None,
    "last_run_at": None,
    "next_run_at": None,
    "running": False,
}
_lock = threading.Lock()
_thread: threading.Thread | None = None
#endregion


#region: helpers
def _set(**kwargs) -> None:
    with _lock:
        _state.update(kwargs)


def _next_run(now, minutes: int):
    return now + timedelta(minutes=minutes)
#endregion


#region: run + loop
def _run_once() -> None:
    """Run one full ingest (imported lazily to avoid a cycle)."""
    _set(running=True)
    try:
        from app.ingest import run_report

        run_report(dry_run=False)
    except Exception:  # noqa: BLE001 — a failed ingest must not kill the loop
        logger.exception("scheduled ingest failed")
    finally:
        _set(last_run_at=utcnow(), running=False)


def _loop(first_delay_minutes: float) -> None:
    delay = first_delay_minutes * 60.0
    while True:
        interval = settings.ingest_interval_minutes
        if not interval:
            _set(enabled=False, interval_minutes=None, next_run_at=None)
            return
        _set(interval_minutes=interval)
        time.sleep(delay)
        _run_once()
        _set(next_run_at=_next_run(utcnow(), interval))
        delay = interval * 60.0
#endregion


#region: start / status
def start() -> None:
    """Start the scheduler if enabled (idempotent)."""
    global _thread
    interval = settings.ingest_interval_minutes
    if not interval:
        return
    with _lock:
        if _thread is not None:
            return
        delay = settings.ingest_startup_delay_minutes
        _state.update({"enabled": True, "interval_minutes": interval})
        _state["next_run_at"] = _next_run(utcnow(), delay)
        _thread = threading.Thread(
            target=_loop, args=(delay,), name="ingest-scheduler", daemon=True
        )
        _thread.start()


def status() -> dict:
    """Snapshot of the scheduler's state (datetimes as ISO strings)."""
    with _lock:
        return {
            "enabled": _state["enabled"],
            "interval_minutes": _state["interval_minutes"],
            "last_run_at": _state["last_run_at"].isoformat() if _state["last_run_at"] else None,
            "next_run_at": _state["next_run_at"].isoformat() if _state["next_run_at"] else None,
            "running": _state["running"],
        }
#endregion
