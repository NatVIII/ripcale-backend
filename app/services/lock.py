"""Cross-process ingest lock (F11).

Guards against a scheduled ingest overlapping a manual ingest (or two manual
runs). The lock is a file in the data dir (`ingest.lock`), so it works across
threads, processes, and containers sharing the same `data_dir`.

A held lock is considered **stale after one ingest interval** (`ingest_interval_minutes`),
matching the scheduler's cadence, so a crashed run can't wedge ingest forever.
"""
#region: imports
import os
import time
from pathlib import Path

from app.config import settings
#endregion


#region: constants
LOCKFILE_NAME = "ingest.lock"
#endregion


#region: helpers
def _lock_path() -> Path:
    return Path(settings.data_dir) / LOCKFILE_NAME


def _stale_timeout_seconds() -> float:
    # One poll interval (fall back to 60s = the default interval's cadence).
    minutes = settings.ingest_interval_minutes or 60
    return float(minutes) * 60.0
#endregion


#region: acquire / release
def acquire() -> bool:
    """Try to take the ingest lock; return True on success, False if already held.

    Stale-aware: a lock older than one interval is removed and retaken.
    """
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            age = float("inf")
        if age > _stale_timeout_seconds():
            release()
            return acquire()
        return False
    with os.fdopen(fd, "w") as f:
        f.write(f"pid={os.getpid()}\n")
    return True


def release() -> None:
    """Drop the ingest lock (idempotent)."""
    try:
        _lock_path().unlink()
    except FileNotFoundError:
        pass
#endregion
