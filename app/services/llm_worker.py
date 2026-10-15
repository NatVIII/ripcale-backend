"""Background LLM worker (F65).

A daemon thread (started by the admin app, like the scheduler) that resolves
pending Instagram posts via `app.services.llm.process_one`. Only runs when
`settings.llm_enabled` is true and `settings.deepseek_key` is set.
"""
#region: imports
import logging
import threading
import time

from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import PendingPost, utcnow
from app.services import llm
from app.services.pending import reset_stale_processing
#endregion


logger = logging.getLogger(__name__)


#region: state
_state = {
    "enabled": False,
    "running": False,
    "last_tick_at": None,
    "processed": 0,
}
_lock = threading.RLock()  # reentrant: `start()` calls `_set()` while already holding it
_thread: threading.Thread | None = None
#endregion


#region: helpers
def _set(**kwargs) -> None:
    with _lock:
        _state.update(kwargs)


def _reason() -> str | None:
    if not settings.llm_enabled:
        return "llm_enabled is false"
    if not settings.deepseek_key:
        return "RIPCALE_DEEPSEEK_KEY is not set"
    return None
#endregion


#region: tick
def run_once() -> dict:
    """Resolve up to `llm_max_per_tick` pending posts; return a summary."""
    reason = _reason()
    if reason is not None:
        return {"processed": 0, "enabled": False, "reason": reason}

    _set(running=True)
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
        _set(last_tick_at=utcnow(), running=False)

    _set(processed=_state["processed"] + processed)
    return {"processed": processed, "enabled": True, "reason": None}


def _loop() -> None:
    while True:
        interval = settings.llm_interval_seconds
        if not settings.llm_enabled or not settings.deepseek_key:
            _set(enabled=False)
            return
        time.sleep(interval)
        run_once()
#endregion


#region: start / status
def start() -> None:
    """Start the worker thread if enabled (idempotent)."""
    global _thread
    if not settings.llm_enabled or not settings.deepseek_key:
        _set(enabled=False)
        return
    with _lock:
        if _thread is not None:
            return
        _set(enabled=True)
        _thread = threading.Thread(target=_loop, name="llm-worker", daemon=True)
        _thread.start()


def status() -> dict:
    with _lock:
        return {
            "enabled": _state["enabled"],
            "running": _state["running"],
            "last_tick_at": _state["last_tick_at"].isoformat() if _state["last_tick_at"] else None,
            "processed": _state["processed"],
            "interval_seconds": settings.llm_interval_seconds,
            "reason": _reason(),
        }
#endregion
