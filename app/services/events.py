"""Event query service (pure, unit-testable DB access).

Called from `app/routers/events.py` and `app/routers/feeds.py`.
"""
#region: imports
from datetime import datetime

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Event, Source
#endregion


#region: category helpers
def _categories_set(categories: str | None) -> set[str]:
    if not categories:
        return set()
    return {c for c in categories.split(",") if c}
#endregion


#region: queries
def query_events(
    session: Session,
    start: datetime | None = None,
    end: datetime | None = None,
    category: str | None = None,
    limit: int | None = 200,
) -> list[Event]:
    """List events, optionally filtered by date overlap, category, and limit."""
    stmt = select(Event)
    if start is not None:
        stmt = stmt.where(func.coalesce(Event.end_at, Event.start_at) >= start)
    if end is not None:
        stmt = stmt.where(func.coalesce(Event.start_at, Event.end_at) <= end)
    stmt = stmt.order_by(Event.start_at)

    events = list(session.exec(stmt).all())
    if category is not None:
        events = [e for e in events if category in _categories_set(e.categories)]
    if limit:
        events = events[:limit]
    return events


def get_event(session: Session, event_id: str) -> Event | None:
    return session.get(Event, event_id)


def source_names(session: Session, events: list[Event]) -> dict[int, str]:
    """Map source_id -> source name for a batch of events (one query)."""
    ids = {e.source_id for e in events}
    if not ids:
        return {}
    rows = session.exec(select(Source).where(Source.id.in_(ids))).all()
    return {s.id: s.name for s in rows}
#endregion
