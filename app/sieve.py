"""The sieve: read-only change detection against the DB.

`classify()` is called from `app/ingest.process_source()`. It classifies each
incoming event as new / updated / unchanged relative to what's stored, without
writing anything. It also merges the source's `default_categories` before
hashing, and hosts the `_relevance` hook where future drop-past rules will live.
"""
#region: imports
from sqlmodel import Session, select

from app.identity import content_hash, stable_id
from app.models import Event
from app.schema import ClassifiedEvent, ModuleResult, ScrapedEvent, SieveResult, load_images
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
    "categories",
)
#endregion


#region: relevance hook
def _relevance(events: list[ScrapedEvent]) -> list[ScrapedEvent]:
    # Future home for relevance rules (e.g. drop events that ended in the past).
    # For now this is an intentional pass-through.
    return events
#endregion


#region: default-category merge
def _merge_default_categories(events: list[ScrapedEvent], defaults: list[str]) -> None:
    """Tag every event with the source's default categories (before hashing)."""
    if not defaults:
        return
    for event in events:
        event.categories = sorted(set(event.categories) | set(defaults))
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
        else:
            new_val = getattr(event, field)
            old_val = getattr(old, field)
        if new_val != old_val:
            changed.append(field)
    return changed
#endregion


#region: classification
def classify(session: Session, result: ModuleResult) -> SieveResult:
    """Bucket incoming events into new / updated / unchanged vs the DB."""
    events = _relevance(result.events)
    _merge_default_categories(events, result.source.default_categories)
    ids = [stable_id(result.source.name, e) for e in events]

    existing: dict[str, Event] = {}
    if ids:
        rows = session.exec(select(Event).where(Event.id.in_(ids))).all()
        existing = {row.id: row for row in rows}

    new: list[ClassifiedEvent] = []
    updated: list[ClassifiedEvent] = []
    unchanged = 0

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

    return SieveResult(source=result.source, new=new, updated=updated, unchanged=unchanged)
#endregion
