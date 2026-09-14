"""Event query service (pure, unit-testable DB access).

Called from `app/routers/events.py` and `app/routers/feeds.py`.
"""
#region: imports
from datetime import datetime

from sqlalchemy import func
from sqlmodel import Session, select

from app.identity import content_hash
from app.models import Event, Source, utcnow
from app.schema import ScrapedEvent, load_exdates, load_images
from app.services.categories import resolve_event_categories
#endregion


#region: defaults
DEFAULT_LIMIT = 500  # max events returned by default (single source of truth)
#endregion


#region: queries
def query_events(
    session: Session,
    start: datetime | None = None,
    end: datetime | None = None,
    category: str | None = None,
    limit: int | None = DEFAULT_LIMIT,
) -> list[Event]:
    """List events, optionally filtered by date overlap, category, and limit.

    Ordered by `start_at` descending (furthest in the future first); events with
    a NULL `start_at` sort last. `limit=None`/`0` means no limit.
    """
    stmt = select(Event).where(Event.archived_at.is_(None))
    if start is not None:
        stmt = stmt.where(func.coalesce(Event.end_at, Event.start_at) >= start)
    if end is not None:
        stmt = stmt.where(func.coalesce(Event.start_at, Event.end_at) <= end)
    stmt = stmt.order_by(Event.start_at.desc())

    events = list(session.exec(stmt).all())
    if category is not None:
        events = [e for e in events if category in resolve_event_categories(e.categories)]
    if limit:
        events = events[:limit]
    return events


def get_event(session: Session, event_id: str) -> Event | None:
    event = session.get(Event, event_id)
    if event is not None and event.archived_at is not None:
        return None  # archived events are hidden from the read path
    return event


def set_pinned(session: Session, event_id: str, pinned: bool) -> bool:
    """Set (or clear) the `pinned` flag on an event; returns whether it was found."""
    event = session.get(Event, event_id)
    if event is None:
        return False
    event.pinned = bool(pinned)
    return True


#region: editing (F28)
_EDITABLE_FIELDS = {
    "title", "description", "location", "url", "images", "start_at", "end_at",
    "timezone", "all_day", "rrule", "recurrence_id", "exdates", "redirect_to_id",
    "priority", "categories",
}


def _recompute_hash(event: Event) -> str:
    """Recompute `content_hash` from the event's current (edited) content."""
    scraped = ScrapedEvent(
        title=event.title,
        description=event.description,
        location=event.location,
        url=event.url,
        images=load_images(event.images),
        start_at=event.start_at,
        end_at=event.end_at,
        timezone=event.timezone,
        all_day=event.all_day,
        rrule=event.rrule,
        recurrence_id=event.recurrence_id,
        exdates=load_exdates(event.exdates),
        categories=[c for c in (event.categories or "").split(",") if c],
    )
    return content_hash(scraped)


def update_event(session: Session, event_id: str, fields: dict, *, pinned: bool = True) -> Event | None:
    """Apply normalized field values to an event, pin it, and refresh its hash.

    `fields` maps `Event` attribute names to already-coerced values (datetimes,
    dumped JSON strings, a comma-joined categories string, bools, etc.). Only
    editable fields are applied. Returns the event, or None if missing.
    """
    event = session.get(Event, event_id)
    if event is None:
        return None
    for key, value in fields.items():
        if key in _EDITABLE_FIELDS:
            setattr(event, key, value)
    event.pinned = pinned
    event.updated_at = utcnow()
    event.content_hash = _recompute_hash(event)
    return event
#endregion


def source_names(session: Session, events: list[Event]) -> dict[int, str]:
    """Map source_id -> source name for a batch of events (one query)."""
    ids = {e.source_id for e in events}
    if not ids:
        return {}
    rows = session.exec(select(Source).where(Source.id.in_(ids))).all()
    return {s.id: s.name for s in rows}
#endregion
