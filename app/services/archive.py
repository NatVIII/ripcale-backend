"""Archive (soft-delete) service — F22.

`archive()` finds events that should be hidden from the public read path and
stamps `archived_at` / `archived_reason` instead of deleting them:

- **expired** — fully past the `expire_past_days` window (immediate; rrule-aware
  via `app/services/expiry.is_expired`).
- **removed** — no longer in the source feed (`last_seen_at != last_fetched_at`,
  or never seen) and stale longer than `archive_grace_hours` (F22.01).

Archived events stay in the DB (restore-on-reseen is handled by the
decisionmaker when the event reappears).
"""
#region: imports
from datetime import timedelta

from sqlmodel import Session, select

from app.config import settings
from app.models import Event, Source, utcnow
from app.services.expiry import is_expired
#endregion


#region: candidate predicates
def _removed_candidate(event: Event, fetched_at, now, grace_hours: int | None) -> bool:
    """True when the event is removed-at-source and past the grace period."""
    if grace_hours is None:
        return False
    seen = event.last_seen_at
    if seen is None:
        return True  # never seen since F15 -> stale forever
    if fetched_at is not None and seen == fetched_at:
        return False  # seen this run
    return (now - seen) >= timedelta(hours=grace_hours)
#endregion


#region: archive
def archive(session: Session, now=None, dry_run: bool = True) -> dict:
    """Archive expired + removed events (soft-delete); return a summary report.

    `dry_run=True` only previews (no writes). `now` is the reference time
    (defaults to the current time; injectable for tests).
    """
    now = now or utcnow()
    fetched = {s.id: s.last_fetched_at for s in session.exec(select(Source)).all()}

    candidates: list[tuple[Event, str]] = []
    for event in session.exec(select(Event).where(Event.archived_at.is_(None))).all():
        if is_expired(event.start_at, event.end_at, event.rrule, now, settings.expire_past_days):
            candidates.append((event, "expired"))
        elif _removed_candidate(event, fetched.get(event.source_id), now, settings.archive_grace_hours):
            candidates.append((event, "removed"))

    if not dry_run:
        for event, reason in candidates:
            event.archived_at = now
            event.archived_reason = reason

    return {
        "expired": sum(1 for _, r in candidates if r == "expired"),
        "removed": sum(1 for _, r in candidates if r == "removed"),
        "dry_run": dry_run,
        "preview": [{"id": e.id, "title": e.title, "reason": r} for e, r in candidates],
    }
#endregion
