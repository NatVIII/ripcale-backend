"""Background backup worker (F23).

A daemon thread (started by the admin app, like the scheduler/LLM/overseer
workers) that periodically writes a DB + intake.yaml snapshot via
`app/services/backup.backup_now`. Runs only when `backup_dir` is set and
`backup_interval_hours` is non-zero.
"""
#region: imports
import logging
import threading
import time
from datetime import timedelta

from app.config import settings
from app.models import utcnow
from app.services import backup
#endregion


logger = logging.getLogger(__name__)


#region: state
_state = {
    "enabled": False,
    "running": False,
    "last_run_at": None,
    "next_run_at": None,
    "runs": 0,
}
_lock = threading.RLock()
_thread: threading.Thread | None = None
#endregion


#region: helpers
def _set(**kwargs) -> None:
    with _lock:
        _state.update(kwargs)


def _reason() -> str | None:
    if not (settings.backup_dir or "").strip():
        return "backup_dir is empty (backups disabled)"
    if not settings.backup_interval_hours:
        return "backup_interval_hours is 0 (scheduled backups off)"
    return None
#endregion


#region: run + loop
def run_once() -> dict:
    """Write one snapshot (idempotent; a failure never kills the loop)."""
    _set(running=True)
    try:
        result = backup.backup_now()
        _set(runs=_state["runs"] + 1)
        return {**result, "enabled": True, "reason": None}
    except Exception as exc:  # noqa: BLE001 — a failed backup must not kill the loop
        logger.exception("scheduled backup failed")
        return {"created": False, "reason": str(exc), "enabled": True}
    finally:
        _set(last_run_at=utcnow(), running=False)


def _loop() -> None:
    while True:
        hours = settings.backup_interval_hours
        if not hours or not (settings.backup_dir or "").strip():
            _set(enabled=False, next_run_at=None)
            return
        _set(next_run_at=utcnow() + timedelta(hours=hours))
        time.sleep(hours * 3600.0)
        run_once()
#endregion


#region: start / status
def start() -> None:
    """Start the backup worker if configured (idempotent)."""
    global _thread
    if _reason() is not None:
        _set(enabled=False)
        return
    with _lock:
        if _thread is not None:
            return
        hours = settings.backup_interval_hours
        _set(enabled=True, next_run_at=utcnow() + timedelta(hours=hours))
        _thread = threading.Thread(target=_loop, name="backup-worker", daemon=True)
        _thread.start()


def status() -> dict:
    with _lock:
        return {
            "enabled": _state["enabled"],
            "running": _state["running"],
            "last_run_at": _state["last_run_at"].isoformat() if _state["last_run_at"] else None,
            "next_run_at": _state["next_run_at"].isoformat() if _state["next_run_at"] else None,
            "runs": _state["runs"],
            "interval_hours": settings.backup_interval_hours,
            "reason": _reason(),
        }
#endregion
