"""Background backup worker (F23).

A daemon thread that periodically writes a DB + intake.yaml snapshot via
`app/services/backup.backup_now`. Runs only when `backup_dir` is set and
`backup_interval_hours` is non-zero. Built on `PeriodicWorker`.
"""
#region: imports
import logging

from app.config import settings
from app.models import utcnow
from app.services import backup
from app.workers.base import PeriodicWorker, iso
#endregion


logger = logging.getLogger(__name__)


#region: worker
class BackupWorker(PeriodicWorker):
    name = "backup"

    def __init__(self) -> None:
        super().__init__()
        self._state.update({"runs": 0})

    def interval_seconds(self) -> int | None:
        hours = settings.backup_interval_hours
        return hours * 3600 if hours else None

    def reason(self) -> str | None:
        if not (settings.backup_dir or "").strip():
            return "backup_dir is empty (backups disabled)"
        if not settings.backup_interval_hours:
            return "backup_interval_hours is 0 (scheduled backups off)"
        return None

    def run_once(self) -> dict:
        """Write one snapshot (idempotent; a failure never kills the loop)."""
        self._set(running=True)
        try:
            result = backup.backup_now()
            self._set(runs=self._state["runs"] + 1)
            return {**result, "enabled": True, "reason": None}
        except Exception as exc:  # noqa: BLE001 — a failed backup must not kill the loop
            logger.exception("scheduled backup failed")
            return {"created": False, "reason": str(exc), "enabled": True}
        finally:
            self._set(last_run_at=utcnow(), running=False)

    def status(self) -> dict:
        with self._lock:
            return {
                "enabled": self._state["enabled"],
                "running": self._state["running"],
                "last_run_at": iso(self._state["last_run_at"]),
                "next_run_at": iso(self._state["next_run_at"]),
                "runs": self._state["runs"],
                "interval_hours": settings.backup_interval_hours,
                "reason": self.reason(),
            }
#endregion


#region: module singleton (keeps the existing `start`/`status`/`run_once` API)
_worker = BackupWorker()
start = _worker.start
status = _worker.status
run_once = _worker.run_once
#endregion
