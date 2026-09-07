"""The sieve: read-only change detection against the DB.

`classify()` is called from `app.ingest.process_source()`. It classifies each
incoming event as new / updated / unchanged relative to what's stored, without
writing anything. It fills the source's `default_location` before hashing and
hosts the `_relevance` hook where future drop-past rules will live. (Category
assignment happens upstream, in the categorize stage.)
"""
#region: imports
from sqlmodel import Session, select

from app.identity import content_hash, stable_id
from app.models import Event
from app.schema import ClassifiedEvent, GathererResult, ScrapedEvent, SieveResult, load_exdates, load_images
#endregion


#region: contract
# Contract: Sieve v3 (docs/SIEVE_CONTRACT.md)
CONTRACT_VERSION = 3
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
def _relevance(events: list[ScrapedEvent]) -> list[ScrapedEvent]:
    # Future home for relevance rules (e.g. drop events that ended in the past).
    # For now this is an intentional pass-through.
    return events
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
def classify(session: Session, result: GathererResult) -> SieveResult:
    """Bucket incoming events into new / updated / unchanged vs the DB."""
    events = _relevance(result.events)
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
    )
#endregion
