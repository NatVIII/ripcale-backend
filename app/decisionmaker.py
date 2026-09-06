"""The decisionmaker: policy + persistence (the write half of the pipeline).

`apply()` is called from `app/ingest.process_source()`. It takes the sieve's
verdict and persists new/updated events. For now the policy is a pass-through;
this is where future cross-source heuristics (dedup, manual-over-scraped
priority) will live.
"""
#region: imports
from sqlmodel import Session

from app.models import Event, Source, utcnow
from app.schema import ClassifiedEvent, SieveResult, dump_exdates, dump_images
#endregion


#region: field mapping
def _categories(event: ClassifiedEvent) -> str:
    return ",".join(sorted(set(event.event.categories)))


def _new_event(source_id: int, classified: ClassifiedEvent) -> Event:
    """Build a new Event row from a classified incoming event."""
    e = classified.event
    return Event(
        id=classified.id,
        source_id=source_id,
        uid=e.uid,
        title=e.title,
        description=e.description,
        location=e.location,
        url=e.url,
        images=dump_images(e.images),
        start_at=e.start_at,
        end_at=e.end_at,
        timezone=e.timezone,
        all_day=e.all_day,
        rrule=e.rrule,
        recurrence_id=e.recurrence_id,
        exdates=dump_exdates(e.exdates),
        categories=_categories(classified),
        content_hash=classified.content_hash,
    )


def _apply_update(existing: Event, classified: ClassifiedEvent) -> None:
    """Copy changed fields onto an existing Event and bump updated_at."""
    e = classified.event
    existing.uid = e.uid
    existing.title = e.title
    existing.description = e.description
    existing.location = e.location
    existing.url = e.url
    existing.images = dump_images(e.images)
    existing.start_at = e.start_at
    existing.end_at = e.end_at
    existing.timezone = e.timezone
    existing.all_day = e.all_day
    existing.rrule = e.rrule
    existing.recurrence_id = e.recurrence_id
    existing.exdates = dump_exdates(e.exdates)
    existing.categories = _categories(classified)
    existing.content_hash = classified.content_hash
    existing.updated_at = utcnow()
#endregion


#region: apply
def apply(session: Session, source: Source, sieved: SieveResult) -> dict:
    """Persist the sieve's new + updated events; return a summary report."""
    inserted = 0
    updated = 0

    for classified in sieved.new:
        session.add(_new_event(source.id, classified))
        inserted += 1

    for classified in sieved.updated:
        existing = session.get(Event, classified.id)
        if existing is None:
            session.add(_new_event(source.id, classified))
            inserted += 1
        else:
            _apply_update(existing, classified)
            updated += 1

    return {"inserted": inserted, "updated": updated, "unchanged": sieved.unchanged}
#endregion
