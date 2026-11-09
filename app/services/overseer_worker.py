"""Background overseer worker (F67.01 + F67.02).

A daemon thread that periodically scans for cross-source duplicate candidates
and decides each pair with DeepSeek. Only runs when `settings.overseer_enabled`
is true (and a DeepSeek key is set). Built on `PeriodicWorker`.
"""
#region: imports
import logging

from sqlmodel import Session

from app.config import settings
from app.db import engine
from app.models import utcnow
from app.services import overseer
from app.services.events import source_names
from app.workers.base import PeriodicWorker, iso
#endregion


logger = logging.getLogger(__name__)


#region: worker
class OverseerWorker(PeriodicWorker):
    name = "overseer"

    def __init__(self) -> None:
        super().__init__()
        self._state.update({"last_tick_at": None, "scanned": 0, "pairs": 0, "decisions": 0})

    def interval_seconds(self) -> int | None:
        return settings.overseer_interval_seconds

    def reason(self) -> str | None:
        if not settings.overseer_enabled:
            return "overseer_enabled is false"
        if not settings.deepseek_key:
            return "RIPCALE_DEEPSEEK_KEY is not set"
        return None

    def run_once(self) -> dict:
        """Find candidate pairs, decide each with DeepSeek, propose merges for dups."""
        reason = self.reason()
        if reason is not None:
            return {"pairs": 0, "decisions": [], "merges": 0, "enabled": False, "reason": reason}

        self._set(running=True)
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

            # Propose an event_merge approval for each confirmed duplicate.
            with Session(engine) as session:
                for a, b, decision in decisions:
                    if not decision.same:
                        continue
                    winner, loser = (a, b) if decision.canonical_id == a.id else (b, a)
                    if overseer.propose_merge(session, winner, loser, decision.enrich, decision.reason):
                        merges += 1
                session.commit()

            self._set(
                scanned=self._state["scanned"] + 1,
                pairs=self._state["pairs"] + len(pairs),
                decisions=self._state["decisions"] + len(decisions),
            )
            return {
                "pairs": len(pairs),
                "decisions": [d.model_dump() for _, _, d in decisions],
                "merges": merges,
                "enabled": True,
                "reason": None,
            }
        finally:
            self._set(last_tick_at=utcnow(), running=False)

    def status(self) -> dict:
        with self._lock:
            return {
                "enabled": self._state["enabled"],
                "running": self._state["running"],
                "last_tick_at": iso(self._state["last_tick_at"]),
                "scanned": self._state["scanned"],
                "pairs": self._state["pairs"],
                "decisions": self._state["decisions"],
                "interval_seconds": settings.overseer_interval_seconds,
                "reason": self.reason(),
            }
#endregion


#region: module singleton (keeps the existing `start`/`status`/`run_once` API)
_worker = OverseerWorker()
start = _worker.start
status = _worker.status
run_once = _worker.run_once
#endregion
