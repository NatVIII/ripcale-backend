"""Background ingest scheduler (F11).

A daemon thread that runs the full ingest on a configurable interval, after a
startup cooldown. Only the admin app starts it. Built on `PeriodicWorker`.
"""
#region: imports
import logging
from datetime import datetime, timedelta

from app.config import settings
from app.models import utcnow
from app.workers.base import PeriodicWorker, iso
#endregion


logger = logging.getLogger(__name__)


#region: helpers
def _next_run(now: datetime, minutes: int) -> datetime:
    return now + timedelta(minutes=minutes)
#endregion


#region: worker
class SchedulerWorker(PeriodicWorker):
    name = "ingest-scheduler"

    def interval_seconds(self) -> int | None:
        minutes = settings.ingest_interval_minutes
        return minutes * 60 if minutes else None

    def first_delay_seconds(self) -> float:
        return settings.ingest_startup_delay_minutes * 60.0

    def run_once(self) -> dict:
        self._set(running=True)
        try:
            from app.ingest import run_report

            run_report(dry_run=False)
            return {"ran": True}
        except Exception:  # noqa: BLE001 — a failed ingest must not kill the loop
            logger.exception("scheduled ingest failed")
            return {"ran": False}
        finally:
            self._set(last_run_at=utcnow(), running=False)

    def status(self) -> dict:
        with self._lock:
            return {
                "enabled": self._state["enabled"],
                "interval_minutes": settings.ingest_interval_minutes,
                "last_run_at": iso(self._state["last_run_at"]),
                "next_run_at": iso(self._state["next_run_at"]),
                "running": self._state["running"],
            }
#endregion


#region: module singleton (keeps the existing `start`/`status` API)
_worker = SchedulerWorker()
start = _worker.start
status = _worker.status
#endregion
