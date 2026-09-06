"""Serialization: DB `Event` -> FullCalendar event object.

Called from `app/routers/events.py`. Produces the FullCalendar `event-parsing`
shape (`id`, `title`, `start`, `end`, `allDay`, `url`, `extendedProps`).
"""
#region: imports
from datetime import datetime

from app.models import Event
from app.schema import load_images
#endregion


#region: field helpers
def _iso(dt: datetime | None, all_day: bool = False) -> str | None:
    """Format a naive-UTC datetime: `...Z` for timed, date-only for all-day."""
    if dt is None:
        return None
    if all_day:
        return dt.date().isoformat()
    return dt.isoformat() + "Z"


def _split_categories(categories: str | None) -> list[str]:
    if not categories:
        return []
    return [c for c in categories.split(",") if c]
#endregion


#region: serializer
def to_fullcalendar(event: Event, source_name: str | None = None) -> dict:
    """Map an Event to FullCalendar's event format (extra data in extendedProps)."""
    props = {
        "description": event.description,
        "location": event.location,
        "categories": _split_categories(event.categories),
        "images": [{"url": img.url, "alt": img.alt, "source_url": img.source_url} for img in load_images(event.images)],
        "timezone": event.timezone,
        "rrule": event.rrule,
    }
    if source_name:
        props["source"] = source_name

    return {
        "id": event.id,
        "title": event.title,
        "start": _iso(event.start_at, event.all_day),
        "end": _iso(event.end_at, event.all_day),
        "allDay": event.all_day,
        "url": event.url,
        "extendedProps": props,
    }
#endregion
