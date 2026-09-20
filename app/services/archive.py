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
from app.services.clock import now as clock_now
from app.services.events import DEFAULT_LIMIT
from app.services.expiry import is_expired
#endregion


#region: constants
DEFAULT_ARCHIVE_LIMIT = DEFAULT_LIMIT  # same default cap as the event listing
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
def archive(session: Session, now=None, dry_run: bool = True, limit: int | None = DEFAULT_ARCHIVE_LIMIT) -> dict:
    """Archive expired + removed events (soft-delete); return a summary report.

    `dry_run=True` only previews (no writes). `now` is the reference time
    (defaults to the current time; injectable for tests). The `preview` list is
    capped at `limit` (most-recent reference time first) while the counts stay
    complete; `limit=None`/`0` = uncapped.
    """
    now = now or clock_now()
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

    ordered = sorted(
        candidates,
        key=lambda e_r: e_r[0].end_at or e_r[0].start_at or now,
        reverse=True,
    )
    if limit:
        ordered = ordered[:limit]

    return {
        "expired": sum(1 for _, r in candidates if r == "expired"),
        "removed": sum(1 for _, r in candidates if r == "removed"),
        "dry_run": dry_run,
        "preview": [{"id": e.id, "title": e.title, "reason": r} for e, r in ordered],
    }
#endregion


#region: listing + restore
def list_archived(session: Session, limit: int | None = DEFAULT_ARCHIVE_LIMIT) -> list[dict]:
    """List archived events, most-recently-archived first (capped at `limit`)."""
    rows = session.exec(
        select(Event).where(Event.archived_at.is_not(None)).order_by(Event.archived_at.desc())
    ).all()
    if limit:
        rows = rows[:limit]
    names = {s.id: s.name for s in session.exec(select(Source)).all()}
    return [
        {
            "id": e.id,
            "title": e.title,
            "source": names.get(e.source_id),
            "archived_at": e.archived_at.isoformat() if e.archived_at else None,
            "archived_reason": e.archived_reason,
            "pinned": e.pinned,
        }
        for e in rows
    ]


def restore(session: Session, event_id: str) -> bool:
    """Un-archive one event (no-op when missing or not archived); returns success."""
    event = session.get(Event, event_id)
    if event is None or event.archived_at is None:
        return False
    event.archived_at = None
    event.archived_reason = None
    return True
#endregion
