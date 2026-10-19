"""Background overseer worker (F67.01 + F67.02).

A daemon thread (started by the admin app, like the scheduler and LLM worker)
that periodically scans for cross-source duplicate candidates and decides each
pair with DeepSeek. Only runs when `settings.overseer_enabled` is true (and a
DeepSeek key is set). F67.03 will turn `same=True` decisions into approval
proposals and apply elevate/redirect on approval.
"""
#region: imports
import logging
import threading
import time

from sqlmodel import Session

from app.config import settings
from app.db import engine
from app.models import utcnow
from app.services import overseer
from app.services.events import source_names
#endregion


logger = logging.getLogger(__name__)


#region: state
_state = {
    "enabled": False,
    "running": False,
    "last_tick_at": None,
    "scanned": 0,   # ticks run
    "pairs": 0,     # candidate pairs found (cumulative)
    "decisions": 0,  # decisions made (cumulative)
}
_lock = threading.RLock()
_thread: threading.Thread | None = None
#endregion


#region: helpers
def _set(**kwargs) -> None:
    with _lock:
        _state.update(kwargs)


def _reason() -> str | None:
    if not settings.overseer_enabled:
        return "overseer_enabled is false"
    if not settings.deepseek_key:
        return "RIPCALE_DEEPSEEK_KEY is not set"
    return None
#endregion


#region: tick
def run_once() -> dict:
    """Find candidate pairs, decide each with DeepSeek, propose merges for dups."""
    reason = _reason()
    if reason is not None:
        return {"pairs": 0, "decisions": [], "merges": 0, "enabled": False, "reason": reason}

    _set(running=True)
    decisions = []
    merges = 0
    try:
        with Session(engine) as session:
            pairs = overseer.find_candidate_pairs(
                session,
                window_days=settings.overseer_window_days,
                similarity_threshold=settings.overseer_similarity_threshold,
            )[: settings.overseer_max_per_tick]
            names = source_names(session, [e for pair in pairs for e in pair])

        for a, b in pairs:
            try:
                decisions.append((a, b, overseer.decide_pair(a, b, source_names=names)))
            except Exception:  # noqa: BLE001 — one bad pair must not stop the loop
                logger.exception("overseer decision failed for pair %s / %s", a.id, b.id)

        # F67.03: propose an event_merge approval for each confirmed duplicate.
        with Session(engine) as session:
            for a, b, decision in decisions:
                if not decision.same:
                    continue
                winner, loser = (a, b) if decision.canonical_id == a.id else (b, a)
                if overseer.propose_merge(session, winner, loser, decision.enrich, decision.reason):
                    merges += 1
            session.commit()

        _set(
            scanned=_state["scanned"] + 1,
            pairs=_state["pairs"] + len(pairs),
            decisions=_state["decisions"] + len(decisions),
        )
        return {
            "pairs": len(pairs),
            "decisions": [d.model_dump() for _, _, d in decisions],
            "merges": merges,
            "enabled": True,
            "reason": None,
        }
    finally:
        _set(last_tick_at=utcnow(), running=False)


def _loop() -> None:
    while True:
        interval = settings.overseer_interval_seconds
        if not settings.overseer_enabled:
            _set(enabled=False)
            return
        time.sleep(interval)
        run_once()
#endregion


#region: start / status
def start() -> None:
    """Start the overseer worker thread if enabled (idempotent)."""
    global _thread
    if not settings.overseer_enabled:
        _set(enabled=False)
        return
    with _lock:
        if _thread is not None:
            return
        _set(enabled=True)
        _thread = threading.Thread(target=_loop, name="overseer-worker", daemon=True)
        _thread.start()


def status() -> dict:
    with _lock:
        return {
            "enabled": _state["enabled"],
            "running": _state["running"],
            "last_tick_at": _state["last_tick_at"].isoformat() if _state["last_tick_at"] else None,
            "scanned": _state["scanned"],
            "pairs": _state["pairs"],
            "decisions": _state["decisions"],
            "interval_seconds": settings.overseer_interval_seconds,
            "reason": _reason(),
        }
#endregion
