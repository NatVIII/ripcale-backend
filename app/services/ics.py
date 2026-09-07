"""ICS generation: DB `Event` -> RFC 5545 calendar.

`events_to_ics()` is called from `app/routers/feeds.py`. Uses standard
properties where possible (UID, SUMMARY, DTSTART/DTEND, DESCRIPTION, X-ALT-DESC,
LOCATION, URL, ATTACH, CATEGORIES) plus `X-RVA-*` custom props — compliant
clients ignore unknown properties.
"""
#region: imports
import re
from datetime import datetime, timezone
from html import unescape

from icalendar import Calendar, Event as VEvent, vRecur

from app.models import Event
from app.schema import load_exdates, load_images
from app.services.categories import resolve_event_categories
#endregion


#region: value helpers
def _utc(dt: datetime) -> datetime:
    """Attach UTC so icalendar emits a `Z`-suffixed timestamp."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _strip_html(value: str) -> str:
    """Convert HTML to plain text for DESCRIPTION."""
    text = re.sub(r"<(br|/p|/div|/li)[^>]*>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).strip()


def _sanitize_html(value: str) -> str:
    """Collapse newlines in HTML (icalendar refuses unescaped newlines)."""
    return re.sub(r"[\r\n]+", " ", value)
#endregion


#region: event -> VEVENT
def event_to_vevent(event: Event, source_name: str | None = None) -> VEvent:
    """Map one Event to an icalendar VEVENT."""
    v = VEvent()
    v.add("uid", event.id)
    v.add("summary", event.title)

    if event.start_at is not None:
        if event.all_day:
            v.add("dtstart", event.start_at.date())
            if event.end_at is not None:
                v.add("dtend", event.end_at.date())
        else:
            v.add("dtstart", _utc(event.start_at))
            if event.end_at is not None:
                v.add("dtend", _utc(event.end_at))

    if event.updated_at is not None:
        v.add("dtstamp", _utc(event.updated_at))

    if event.description:
        v.add("description", _strip_html(event.description))
        v.add("x-alt-desc", _sanitize_html(event.description), parameters={"FMTTYPE": "text/html"})
    if event.location:
        v.add("location", event.location)
    if event.url:
        v.add("url", event.url)
    images = load_images(event.images)
    for image in images:
        v.add("attach", image.url)
    if images:
        v.add("x-rva-image", images[0].url)
    if event.rrule:
        v.add("rrule", vRecur.from_ical(event.rrule))
    for exdate in load_exdates(event.exdates):
        v.add("exdate", exdate.date() if event.all_day else _utc(exdate))
    if event.recurrence_id is not None:
        v.add("recurrence-id", event.recurrence_id.date() if event.all_day else _utc(event.recurrence_id))
    if event.categories:
        v.add("categories", resolve_event_categories(event.categories))
    if event.timezone:
        v.add("x-rva-timezone", event.timezone)
    if source_name:
        v.add("x-rva-source", source_name)

    return v
#endregion


#region: calendar assembly
def events_to_ics(
    events: list[Event],
    names: dict[int, str] | None = None,
    title: str = "rva.rip",
) -> str:
    """Build a complete VCALENDAR string from a list of events."""
    cal = Calendar()
    cal.add("prodid", "-//rva.rip//ripcale//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", title)
    for event in events:
        cal.add_component(event_to_vevent(event, (names or {}).get(event.source_id)))
    return cal.to_ical().decode("utf-8")
#endregion
