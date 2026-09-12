"""Recurrence helpers (RFC 5545 RRULE).

`last_occurrence()` is used by the sieve's expiry filter (F13) and the garbage
collector (F22) to decide whether a recurring series has fully ended. F12
(recurrence expansion) will build the full occurrence generator here too.
"""
#region: imports
from datetime import date, datetime, time

from dateutil.rrule import rrulestr
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
    try:
        rule = rrulestr(rrule_str, dtstart=start_at)
        last = rule[-1]  # raises ValueError when the rule is unbounded
    except Exception:  # noqa: BLE001 — any parse/expansion failure -> None
        return None
    if isinstance(last, datetime):
        return last
    if isinstance(last, date):  # all-day UNTIL may come back as a date
        return datetime.combine(last, time.min)
    return None
#endregion
