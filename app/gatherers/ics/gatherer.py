"""ICS (iCalendar / RFC 5545) gatherer — F25.

Fetches an `.ics` feed (e.g. a public Google Calendar) and maps every `VEVENT`
into the shared `ScrapedEvent` shape. Generic over any RFC 5545 source — no
Google-specific assumptions.
"""
# Contract: Gatherer v4 (docs/GATHERER_CONTRACT.md)
CONTRACT_VERSION = 4

#region: imports
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from icalendar import Calendar

from app.gatherers.base import fetch_text
from app.schema import GathererResult, ImageRef, ScrapedEvent, SourceConfig
from app.timeutil import to_utc_naive
#endregion


#region: field helpers
def _text(component, name: str) -> str | None:
    value = component.get(name)
    return str(value) if value is not None else None


def _parse_dt(vddt) -> tuple[datetime | None, bool]:
    """Return (naive-UTC datetime | None, is_all_day) from a DTSTART/DTEND value."""
    if vddt is None:
        return None, False
    dt = vddt.dt
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            return to_utc_naive(dt), False
        tzid = vddt.params.get("TZID")
        if tzid:
            try:
                return to_utc_naive(dt.replace(tzinfo=ZoneInfo(tzid))), False
            except (ZoneInfoNotFoundError, ValueError):
                return dt, False  # unknown zone -> treat as UTC
        return dt, False  # Z-suffixed (UTC) or floating -> assume UTC
    if isinstance(dt, date):
        return datetime.combine(dt, time.min), True  # VALUE=DATE -> all-day
    return None, False


def _to_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return to_utc_naive(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    return None


def _images(component) -> list[ImageRef]:
    attach = component.get("ATTACH")
    if attach is None:
        return []
    items = attach if isinstance(attach, list) else [attach]
    out: list[ImageRef] = []
    for item in items:
        fmt = (item.params.get("FMTTYPE") or "").lower()
        if fmt.startswith("image/"):
            out.append(ImageRef(url=str(item)))
    return out
#endregion


#region: event mapping
def _event(component, cal_tz: str | None) -> ScrapedEvent:
    status = _text(component, "STATUS")
    categories = [str(c) for c in (component.get("CATEGORIES") or [])]
    if status:
        categories.append(status.lower())  # confirmed / tentative / cancelled / …

    start, start_all_day = _parse_dt(component.get("DTSTART"))
    end, _ = _parse_dt(component.get("DTEND"))

    rrule = component.get("RRULE")
    rrule_str = rrule.to_ical().decode() if rrule is not None else None

    rec_id = component.get("RECURRENCE-ID")
    recurrence_id = _to_datetime(rec_id.dt) if rec_id is not None else None

    exd = component.get("EXDATE")
    exdates = [_to_datetime(x.dt) for x in exd.dts if _to_datetime(x.dt) is not None] if exd is not None else []

    dtstart = component.get("DTSTART")
    tzid = dtstart.params.get("TZID") if dtstart is not None else None

    return ScrapedEvent(
        uid=_text(component, "UID"),
        title=_text(component, "SUMMARY") or "(untitled)",
        description=_text(component, "DESCRIPTION"),
        location=_text(component, "LOCATION"),
        url=_text(component, "URL"),
        images=_images(component),
        start_at=start,
        end_at=end,
        timezone=tzid or cal_tz,
        all_day=start_all_day,
        rrule=rrule_str,
        recurrence_id=recurrence_id,
        exdates=exdates,
        categories=categories,
        raw={
            "status": status,
            "sequence": _text(component, "SEQUENCE"),
            "dtstamp": _text(component, "DTSTAMP"),
            "created": _text(component, "CREATED"),
            "last_modified": _text(component, "LAST-MODIFIED"),
            "transp": _text(component, "TRANSP"),
        },
    )
#endregion


#region: entry point
def run(source: SourceConfig) -> GathererResult:
    """Fetch + parse an ICS feed into a GathererResult."""
    text = fetch_text(source.url)
    cal = Calendar.from_ical(text)
    cal_tz = _text(cal, "X-WR-TIMEZONE")
    events = [_event(c, cal_tz) for c in cal.walk("VEVENT")]
    return GathererResult(source=source, events=events)
#endregion
