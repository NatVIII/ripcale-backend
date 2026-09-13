"""Recurrence helpers (RFC 5545 RRULE).

`last_occurrence()` is used by the sieve's expiry filter (F13) and the garbage
collector (F22) to decide whether a recurring series has fully ended. F12
(recurrence expansion) will build the full occurrence generator here too.
"""
#region: imports
import re
from datetime import date, datetime, time

from dateutil.rrule import rrulestr
#endregion


#region: normalization
_UNTIL_ISO = re.compile(
    r"UNTIL=(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}):(\d{2}))?Z?",
    re.IGNORECASE,
)
_UNTIL_Z = re.compile(r"(UNTIL=\d{8}(?:T\d{6})?)Z", re.IGNORECASE)


def _normalize_until(rrule_str: str) -> str:
    """Rewrite `UNTIL` into the compact form dateutil accepts.

    Real calendars emit RFC 5545 `UNTIL` values dateutil's `rrulestr` rejects:
    a trailing `Z` (`UNTIL=20240129T000000Z`) and ISO-dashed dates
    (`UNTIL=2024-01-29T00:00:00Z`). This collapses both to `UNTIL=YYYYMMDDTHHMMSS`
    (or `YYYYMMDD` for date-only), and strips the `Z`.
    """
    def _rebuild(m):
        date_ = f"{m.group(1)}{m.group(2)}{m.group(3)}"
        if m.group(4):
            return f"UNTIL={date_}T{m.group(4)}{m.group(5)}{m.group(6)}"
        return f"UNTIL={date_}"

    return _UNTIL_Z.sub(r"\1", _UNTIL_ISO.sub(_rebuild, rrule_str))
#endregion


#region: last occurrence
def last_occurrence(rrule_str: str | None, start_at: datetime | None) -> datetime | None:
    """Return the final occurrence of a bounded RRULE, or None.

    None means "no determinable last occurrence": the series is unbounded (no
    `UNTIL`/`COUNT`), unparseable, or `start_at` is missing. Callers treat None
    as "never expires" (fail-safe — over-keeping is better than over-dropping).
    """
    if not rrule_str or start_at is None:
        return None

    normalized = _normalize_until(rrule_str)
    upper = normalized.upper()
    if "COUNT=" not in upper and "UNTIL=" not in upper:
        return None  # unbounded series has no last occurrence

    try:
        rule = rrulestr(normalized, dtstart=start_at)
        last = rule[-1]
    except Exception:  # noqa: BLE001 — any parse/expansion failure -> None
        return None
    if isinstance(last, datetime):
        return last
    if isinstance(last, date):  # all-day UNTIL may come back as a date
        return datetime.combine(last, time.min)
    return None
#endregion
