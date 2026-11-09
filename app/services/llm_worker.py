"""Background LLM worker (F65).

A daemon thread that resolves pending Instagram posts via
`app.services.llm.process_one`. Only runs when `settings.llm_enabled` is true and
`settings.deepseek_key` is set. Built on `PeriodicWorker`.
"""
#region: imports
import logging

from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import PendingPost, utcnow
from app.services import llm
from app.services.pending import reset_stale_processing
from app.workers.base import PeriodicWorker, iso
#endregion


logger = logging.getLogger(__name__)


#region: worker
class LlmWorker(PeriodicWorker):
    name = "llm"

    def __init__(self) -> None:
        super().__init__()
        self._state.update({"last_tick_at": None, "processed": 0})

    def interval_seconds(self) -> int | None:
        return settings.llm_interval_seconds

    def reason(self) -> str | None:
        if not settings.llm_enabled:
            return "llm_enabled is false"
        if not settings.deepseek_key:
            return "RIPCALE_DEEPSEEK_KEY is not set"
        return None

    def run_once(self) -> dict:
        """Resolve up to `llm_max_per_tick` pending posts; return a summary."""
        reason = self.reason()
        if reason is not None:
            return {"processed": 0, "enabled": False, "reason": reason}

        self._set(running=True)
        try:
            with Session(engine) as session:
                reset_stale_processing(session, settings.llm_stale_processing_seconds)
                session.commit()
                posts = session.exec(
                    select(PendingPost)
                    .where(PendingPost.status == "pending")
                    .order_by(PendingPost.created_at)
                    .limit(settings.llm_max_per_tick)
                ).all()
                uids = [p.uid for p in posts]

            processed = 0
            for uid in uids:
                try:
                    llm.process_one(uid)
                    processed += 1
                except Exception:  # noqa: BLE001 — one bad post must not stop the loop
                    logger.exception("llm process failed for post %s", uid)
        finally:
            self._set(last_tick_at=utcnow(), running=False)

        self._set(processed=self._state["processed"] + processed)
        return {"processed": processed, "enabled": True, "reason": None}

    def status(self) -> dict:
        with self._lock:
            return {
                "enabled": self._state["enabled"],
                "running": self._state["running"],
                "last_tick_at": iso(self._state["last_tick_at"]),
                "processed": self._state["processed"],
                "interval_seconds": settings.llm_interval_seconds,
                "reason": self.reason(),
            }
#endregion


#region: module singleton (keeps the existing `start`/`status`/`run_once` API)
_worker = LlmWorker()
start = _worker.start
status = _worker.status
run_once = _worker.run_once
#endregion
