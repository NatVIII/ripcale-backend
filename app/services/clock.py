"""Central "now" source (F56.01).

`now()` returns the current naive-UTC datetime, or a fixed debug instant when
`settings.debug_now` is set (for bug reproduction / time-travel). Pipeline logic
that reasons about "now" (expiry, relevance, archive, stale/upcoming counts)
should call `clock.now()`; security (auth session expiry) and audit timestamps
(`created_at`/`updated_at`) stay on the real wall clock.
"""
#region: imports
from datetime import datetime

from app.config import settings
from app.models import utcnow
from app.timeutil import to_utc_naive
#endregion


#region: cache
_cache: dict = {"raw": None, "value": None}
#endregion


#region: debug instant
def _parse(raw: str) -> datetime | None:
    try:
        return to_utc_naive(datetime.fromisoformat(raw))
    except (TypeError, ValueError):
        return None


def _debug_now() -> datetime | None:
    raw = settings.debug_now
    if raw != _cache["raw"]:
        _cache["raw"] = raw
        _cache["value"] = _parse(raw) if raw else None
    return _cache["value"]
#endregion


#region: public API
def now() -> datetime:
    """The pipeline's current time (naive UTC); frozen when `debug_now` is set."""
    return _debug_now() or utcnow()


def debug_active() -> bool:
    """Whether a debug clock override is in effect."""
    return _debug_now() is not None
#endregion
