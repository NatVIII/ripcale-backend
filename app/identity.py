"""Stable identity + change detection for events.

Called from `app/sieve.py`. `stable_id()` keys an event into the DB; `content_hash()`
fingerprints its mutable fields so the sieve can tell "changed" from "unchanged".
"""
#region: imports
import hashlib
import json

from app.schema import ScrapedEvent
#endregion


#region: stable id
def stable_id(source_name: str, event: ScrapedEvent) -> str:
    """A deterministic id = sha256(source + uid). Falls back to title|start."""
    if event.uid:
        key = f"{source_name}:{event.uid}"
    else:
        start = event.start_at.isoformat() if event.start_at else ""
        key = f"{source_name}:{event.title}|{start}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
#endregion


#region: content hash
def content_hash(event: ScrapedEvent) -> str:
    """Fingerprint the mutable fields (excludes uid + raw)."""
    payload = {
        "title": event.title,
        "description": event.description,
        "location": event.location,
        "url": event.url,
        "images": [img.model_dump() for img in event.images],
        "start_at": event.start_at.isoformat() if event.start_at else None,
        "end_at": event.end_at.isoformat() if event.end_at else None,
        "timezone": event.timezone,
        "all_day": event.all_day,
        "rrule": event.rrule,
        "categories": sorted(event.categories),
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
#endregion
