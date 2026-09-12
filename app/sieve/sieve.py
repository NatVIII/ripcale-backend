"""The sieve: read-only change detection against the DB.

`classify()` is called from `app.ingest.process_source()`. It classifies each
incoming event as new / updated / unchanged relative to what's stored, without
writing anything. It drops irrelevant events via `_relevance` (the F13
expiry filter: events too old or too far in the future), then fills the source's
`default_location` before hashing. (Category assignment happens upstream, in the
categorize stage.)
"""
#region: imports
from sqlmodel import Session, select

from app.config import settings
from app.identity import content_hash, stable_id
from app.models import Event, utcnow
from app.schema import ClassifiedEvent, GathererResult, ScrapedEvent, SieveResult, load_exdates, load_images
from app.services import expiry
#endregion


#region: contract
# Contract: Sieve v4 (docs/SIEVE_CONTRACT.md)
CONTRACT_VERSION = 4
#endregion


#region: change-detection constants
_CHANGED_FIELDS = (
    "title",
    "description",
    "location",
    "url",
    "images",
    "start_at",
    "end_at",
    "timezone",
    "all_day",
    "rrule",
    "exdates",
    "categories",
)
#endregion


#region: relevance hook
def _relevance(events: list[ScrapedEvent], now) -> list[ScrapedEvent]:
    """Drop events outside the configured relevance window (F13).

    `expire_past_days` drops events that fully ended too long ago (recurring
    series only once their last occurrence has passed); `expire_future_days`
    drops events starting too far ahead. Both `None` = pass-through.
    """
    past_days = settings.expire_past_days
    future_days = settings.expire_future_days
    if past_days is None and future_days is None:
        return events
    return [
        e for e in events
        if expiry.is_relevant(e.start_at, e.end_at, e.rrule, now, past_days, future_days)
    ]
#endregion


#region: default-location merge
def _merge_default_location(events: list[ScrapedEvent], default: str | None) -> None:
    """Fill missing/blank locations with the source's default (before hashing)."""
    if not default:
        return
    for event in events:
        if not event.location or not event.location.strip():
            event.location = default
#endregion


#region: field diffing
def _changed_fields(event: ScrapedEvent, old: Event) -> list[str]:
    """Return which mutable fields differ between an incoming event and a stored one."""
    changed: list[str] = []
    for field in _CHANGED_FIELDS:
        if field == "categories":
            new_val = sorted(event.categories)
            old_val = sorted(old.categories.split(",")) if old.categories else []
        elif field == "images":
            new_val = event.images
            old_val = load_images(old.images)
        elif field == "exdates":
            new_val = event.exdates
            old_val = load_exdates(old.exdates)
        else:
            new_val = getattr(event, field)
            old_val = getattr(old, field)
        if new_val != old_val:
            changed.append(field)
    return changed
#endregion


#region: classification
def classify(session: Session, result: GathererResult, *, now=None) -> SieveResult:
    """Bucket incoming events into new / updated / unchanged vs the DB.

    `now` is the relevance reference time (defaults to the current UTC time;
    injectable so tests stay deterministic).
    """
    if now is None:
        now = utcnow()
    events = _relevance(result.events, now)
    dropped = len(result.events) - len(events)
    _merge_default_location(events, result.source.default_location)
    ids = [stable_id(result.source.name, e) for e in events]

    existing: dict[str, Event] = {}
    if ids:
        rows = session.exec(select(Event).where(Event.id.in_(ids))).all()
        existing = {row.id: row for row in rows}

    new: list[ClassifiedEvent] = []
    updated: list[ClassifiedEvent] = []
    unchanged = 0
    unchanged_ids: list[str] = []

    for event, event_id in zip(events, ids):
        digest = content_hash(event)
        old = existing.get(event_id)
        if old is None:
            new.append(ClassifiedEvent(id=event_id, content_hash=digest, event=event))
        elif old.content_hash != digest:
            updated.append(
                ClassifiedEvent(
                    id=event_id,
                    content_hash=digest,
                    event=event,
                    changed_fields=_changed_fields(event, old),
                )
            )
        else:
            unchanged += 1
            unchanged_ids.append(event_id)

    return SieveResult(
        source=result.source,
        new=new,
        updated=updated,
        unchanged=unchanged,
        unchanged_ids=unchanged_ids,
        dropped=dropped,
    )
#endregion
