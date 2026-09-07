"""Elfsight event-calendar widget gatherer.

`run(source)` is the gatherer entry point: called by `app.registry.load_gatherer()`
/ `app.ingest.process_source()`. It fetches the Elfsight "boot" JSON endpoint,
resolves the eventType/location ID lookups, and maps each event into a
`ScrapedEvent`.
"""
# Contract: Gatherer v2 (docs/GATHERER_CONTRACT.md)
CONTRACT_VERSION = 2

#region: imports
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from app.schema import ImageRef, GathererResult, ScrapedEvent, SourceConfig
from app.gatherers.base import fetch_json
from app.timeutil import to_utc_naive
#endregion


#region: url parsing
def _widget_id_from_url(url: str) -> str | None:
    query = parse_qs(urlparse(url).query)
    return query.get("w", [None])[0]
#endregion


#region: field parsing
def _parse_datetime(value: dict, tz_name: str | None) -> datetime | None:
    """Combine {date, time} with the event timezone, returned as naive UTC."""
    date = value.get("date")
    if not date:
        return None
    time = value.get("time") or "00:00"
    dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    if tz_name:
        dt = dt.replace(tzinfo=ZoneInfo(tz_name))
    return to_utc_naive(dt)


def _images(raw: dict) -> list[ImageRef]:
    """Extract the ordered gallery (falls back to coverImage if images empty)."""
    entries = raw.get("images") or []
    result = [
        ImageRef(url=entry["url"], alt=entry.get("alt"))
        for entry in entries
        if entry.get("url")
    ]
    if not result:
        cover = raw.get("coverImage")
        if isinstance(cover, dict) and cover.get("url"):
            result = [ImageRef(url=cover["url"], alt=cover.get("alt"))]
        elif isinstance(cover, str) and cover:
            result = [ImageRef(url=cover)]
    return result


def _action_url(raw: dict) -> str | None:
    for action in raw.get("actions") or []:
        link = action.get("link") or {}
        if link.get("type") == "url" and link.get("value"):
            return link["value"]
    return None
#endregion


#region: event mapping
def _parse_event(raw: dict, types: dict, locations: dict) -> ScrapedEvent:
    """Map one raw Elfsight event into a normalized ScrapedEvent."""
    tz_name = raw.get("timeZone")

    type_ids = raw.get("eventType") or []
    categories = [types[t] for t in type_ids if t in types]

    loc_ids = raw.get("location") or []
    location = None
    if loc_ids and loc_ids[0] in locations:
        location = locations[loc_ids[0]]

    return ScrapedEvent(
        uid=raw.get("id"),
        title=raw.get("name") or "(untitled)",
        description=raw.get("description") or None,
        location=location,
        url=_action_url(raw),
        images=_images(raw),
        start_at=_parse_datetime(raw.get("start") or {}, tz_name),
        end_at=_parse_datetime(raw.get("end") or {}, tz_name),
        timezone=tz_name,
        all_day=bool(raw.get("isAllDay", False)),
        categories=categories,
        raw=raw,
    )
#endregion


#region: entry point
def run(source: SourceConfig) -> GathererResult:
    """Fetch + parse an Elfsight widget boot payload into a GathererResult."""
    data = fetch_json(source.url)
    widgets = data.get("data", {}).get("widgets", {})

    widget_id = _widget_id_from_url(source.url)
    if not widget_id or widget_id not in widgets:
        widget_id = next(iter(widgets), None)
    if widget_id is None:
        raise ValueError("no widget found in Elfsight response")

    settings = widgets[widget_id]["data"]["settings"]
    types = {t["id"]: t["name"] for t in settings.get("eventTypes", [])}
    locations = {l["id"]: l["name"] for l in settings.get("locations", [])}

    events = [
        _parse_event(raw, types, locations)
        for raw in settings.get("events", [])
    ]
    return GathererResult(source=source, events=events)
#endregion
