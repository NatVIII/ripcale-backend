"""Shared expiry/relevance window (F13 sieve relevance; F22 GC reuses the cutoffs).

All datetimes are naive UTC (see `app/models.py`). Cutoffs are `None` when the
corresponding limit is disabled (no filtering).
"""
#region: imports
from datetime import datetime, timedelta

from app.services.recurrence import last_occurrence
#endregion


#region: cutoffs
def past_cutoff(now: datetime, days: int | None) -> datetime | None:
    """The moment `days` ago (None = no past limit)."""
    if days is None:
        return None
    return now - timedelta(days=days)


def future_cutoff(now: datetime, days: int | None) -> datetime | None:
    """The moment `days` ahead (None = no future limit)."""
    if days is None:
        return None
    return now + timedelta(days=days)
#endregion


#region: relevance
def is_past_expired(end_at: datetime | None, start_at: datetime | None, now: datetime, days: int | None) -> bool:
    """True when the event has fully ended more than `days` ago (null end -> start)."""
    cutoff = past_cutoff(now, days)
    if cutoff is None:
        return False
    end = end_at or start_at
    return end is not None and end < cutoff


def is_future_expired(start_at: datetime | None, now: datetime, days: int | None) -> bool:
    """True when the event starts more than `days` ahead."""
    cutoff = future_cutoff(now, days)
    if cutoff is None:
        return False
    return start_at is not None and start_at > cutoff


def is_relevant(
    start_at: datetime | None,
    end_at: datetime | None,
    rrule: str | None,
    now: datetime,
    past_days: int | None,
    future_days: int | None,
) -> bool:
    """Whether an event falls within the relevant window (both bounds optional).

    Non-recurring events expire when they've fully ended (`end_at`/`start_at`)
    beyond the past window. Recurring events expire only when their **last
    occurrence** (start + duration) is beyond the past window; unbounded or
    unparseable rules never expire. The future bound applies to every event.
    """
    if is_future_expired(start_at, now, future_days):
        return False

    if rrule:
        last = last_occurrence(rrule, start_at)
        if last is None:
            return True  # unbounded/unparseable -> never past-expire
        cutoff = past_cutoff(now, past_days)
        if cutoff is None:
            return True
        duration = (end_at - start_at) if (end_at is not None and start_at is not None) else None
        last_end = last + duration if duration is not None else last
        return last_end >= cutoff

    return not is_past_expired(end_at, start_at, now, past_days)
#endregion
