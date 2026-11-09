"""Shared base for ripcale's periodic background workers (F70.02).

A worker is a daemon thread that calls `run_once()` on a fixed interval. The
base owns the thread lifecycle, the lock, and the common `_state` keys; each
subclass supplies `interval_seconds()`, `run_once()`, and (optionally) `reason()`,
`first_delay_seconds()`, and its own `status()` shape.

This is the seam that replaces the four near-identical worker scaffolds; F74.04
moves the concrete workers into this package.
"""
#region: imports
from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any

from app.models import utcnow
#endregion


logger = logging.getLogger(__name__)


#region: helpers
def iso(value) -> str | None:
    """ISO-format a datetime for status dicts (None passes through)."""
    return value.isoformat() if value else None
#endregion


#region: base
class PeriodicWorker(ABC):
    """A daemon thread that runs `run_once()` every interval."""

    name: str = "worker"

    def __init__(self) -> None:
        self._state: dict[str, Any] = {
            "enabled": False,
            "running": False,
            "last_run_at": None,
            "next_run_at": None,
        }
        self._lock = threading.RLock()  # reentrant: `_set` is safe under `start()`
        self._thread: threading.Thread | None = None

    # -- subclass hooks ------------------------------------------------------
    @abstractmethod
    def interval_seconds(self) -> int | None:
        """Current interval in seconds (None/0 disables the worker)."""

    @abstractmethod
    def run_once(self) -> dict:
        """Perform one tick and return a summary dict."""

    def reason(self) -> str | None:
        """Why the worker is disabled (None = runnable). Override to gate."""
        return None

    def first_delay_seconds(self) -> float:
        """Delay before the first tick (defaults to one interval)."""
        return self.interval_seconds() or 0

    # -- machinery -----------------------------------------------------------
    def _set(self, **kwargs) -> None:
        with self._lock:
            self._state.update(kwargs)

    def start(self) -> None:
        """Start the daemon thread if enabled (idempotent)."""
        if not self.interval_seconds() or self.reason() is not None:
            self._set(enabled=False)
            return
        with self._lock:
            if self._thread is not None:
                return
            self._state["enabled"] = True
            self._state["next_run_at"] = utcnow() + timedelta(seconds=self.first_delay_seconds())
            self._thread = threading.Thread(target=self._loop, name=f"{self.name}-worker", daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        delay = self.first_delay_seconds()
        while True:
            interval = self.interval_seconds()
            if not interval or self.reason() is not None:
                self._set(enabled=False, next_run_at=None)
                return
            self._set(next_run_at=utcnow() + timedelta(seconds=delay))
            time.sleep(delay)
            self.run_once()
            delay = interval
#endregion
