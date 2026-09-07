"""Aggregate, non-secret statistics about the stored data.

Called from `app/debug.py` (CLI) and `app/routers/debug.py` (dashboard).
All functions return plain dicts (JSON-safe) and never expose secret source
URLs or the `raw` source payload (which is not persisted).
"""
#region: imports
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.config import settings
from app.models import Event, Source
from app.schema import load_images
#endregion


#region: helpers
def _now() -> datetime:
    """Current time as a naive UTC datetime (matches stored convention)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
#endregion


#region: overview
def overview(session: Session) -> dict:
    """High-level counts and category breakdown."""
    source_count = len(session.exec(select(Source)).all())
    event_count = session.exec(select(func.count(Event.id))).one()
    upcoming = session.exec(
        select(func.count(Event.id)).where(
            func.coalesce(Event.start_at, Event.end_at) >= _now()
        )
    ).one()
    span = session.exec(select(func.min(Event.start_at), func.max(Event.start_at))).one()

    categories: dict[str, int] = {}
    for cats in session.exec(select(Event.categories)).all():
        for name in (cats or "").split(","):
            name = name.strip()
            if name:
                categories[name] = categories.get(name, 0) + 1

    return {
        "sources": source_count,
        "events": event_count,
        "upcoming": upcoming,
        "past": event_count - upcoming,
        "date_span": {
            "earliest": span[0].isoformat() if span[0] else None,
            "latest": span[1].isoformat() if span[1] else None,
        },
        "categories": [
            {"name": name, "count": count}
            for name, count in sorted(categories.items(), key=lambda kv: -kv[1])
        ],
    }
#endregion


#region: sources
def sources(session: Session) -> list[dict]:
    """Non-secret per-source summary (never the URL)."""
    out = []
    for source in session.exec(select(Source)).all():
        count = session.exec(
            select(func.count(Event.id)).where(Event.source_id == source.id)
        ).one()
        out.append(
            {
                "name": source.name,
                "gatherer": source.gatherer,
                "is_public": source.is_public,
                "last_fetched_at": source.last_fetched_at.isoformat()
                if source.last_fetched_at
                else None,
                "event_count": count,
            }
        )
    return out
#endregion


#region: event dump
def event_dump(session: Session, event_id: str) -> dict | None:
    """Return every stored column of one event (plus its source name)."""
    event = session.get(Event, event_id)
    if event is None:
        return None
    source = session.get(Source, event.source_id)
    return {
        "id": event.id,
        "source": source.name if source else None,
        "uid": event.uid,
        "title": event.title,
        "description": event.description,
        "location": event.location,
        "url": event.url,
        "images": [{"url": img.url, "alt": img.alt, "source_url": img.source_url} for img in load_images(event.images)],
        "start_at": event.start_at.isoformat() if event.start_at else None,
        "end_at": event.end_at.isoformat() if event.end_at else None,
        "timezone": event.timezone,
        "all_day": event.all_day,
        "rrule": event.rrule,
        "recurrence_id": event.recurrence_id.isoformat() if event.recurrence_id else None,
        "exdates": json.loads(event.exdates or "[]"),
        "redirect_to_id": event.redirect_to_id,
        "categories": event.categories,
        "content_hash": event.content_hash,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "updated_at": event.updated_at.isoformat() if event.updated_at else None,
    }
#endregion


#region: stale events
def stale_events(session: Session) -> list[dict]:
    """Return events that were removed at the source (not seen on the latest run).

    An event is stale when its `last_seen_at` differs from its source's
    `last_fetched_at` (or is NULL — never seen since the column was added).
    """
    stale = session.exec(
        select(Event).join(Source, Event.source_id == Source.id).where(
            or_(Event.last_seen_at.is_(None), Event.last_seen_at != Source.last_fetched_at)
        )
    ).all()
    names = {s.id: s.name for s in session.exec(select(Source)).all()}
    out = []
    for event in stale:
        src = names.get(event.source_id)
        out.append(
            {
                "id": event.id,
                "source": src,
                "title": event.title,
                "last_seen_at": event.last_seen_at.isoformat() if event.last_seen_at else None,
            }
        )
    return out
#endregion


#region: last ingest
def read_last_ingest() -> dict | None:
    """Read the last ingest report (written by app.ingest), if present."""
    path = Path(settings.data_dir) / "last_ingest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
#endregion
