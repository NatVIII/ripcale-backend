"""The decisionmaker: policy + persistence (the write half of the pipeline).

`apply()` is called from `app/ingest.process_source()`. It takes the sieve's
verdict and persists new/updated events. For now the policy is a pass-through;
this is where future cross-source heuristics (dedup, manual-over-scraped
priority) will live.
"""
#region: imports
from sqlalchemy import or_
from sqlmodel import Session, select

from app.models import Event, Source, utcnow
from app.schema import ClassifiedEvent, SieveResult, dump_exdates, dump_images
#endregion


#region: field mapping
def _categories(event: ClassifiedEvent) -> str:
    return ",".join(sorted(set(event.event.categories)))


def _new_event(source_id: int, classified: ClassifiedEvent, run_ts) -> Event:
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
        last_seen_at=run_ts,
    )


def _apply_update(existing: Event, classified: ClassifiedEvent, run_ts) -> None:
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
    existing.last_seen_at = run_ts
    existing.updated_at = utcnow()
#endregion


#region: apply
def apply(session: Session, source: Source, sieved: SieveResult) -> dict:
    """Persist the sieve's new + updated events; return a summary report.

    Also stamps `last_seen_at` on every seen event and detects events that were
    previously stored for this source but absent from this run (removed at the
    source). Returns `removed` as the count of those stale events.
    """
    run_ts = utcnow()
    inserted = 0
    updated = 0

    for classified in sieved.new:
        session.add(_new_event(source.id, classified, run_ts))
        inserted += 1

    for classified in sieved.updated:
        existing = session.get(Event, classified.id)
        if existing is None:
            session.add(_new_event(source.id, classified, run_ts))
            inserted += 1
        else:
            _apply_update(existing, classified, run_ts)
            updated += 1

    if sieved.unchanged_ids:
        rows = session.exec(select(Event).where(Event.id.in_(sieved.unchanged_ids))).all()
        for row in rows:
            row.last_seen_at = run_ts

    # Mark the source as fetched at this run's timestamp (shared with last_seen_at).
    source.last_fetched_at = run_ts

    stale = session.exec(
        select(Event).where(
            Event.source_id == source.id,
            or_(Event.last_seen_at.is_(None), Event.last_seen_at != run_ts),
        )
    ).all()

    return {
        "inserted": inserted,
        "updated": updated,
        "unchanged": sieved.unchanged,
        "removed": len(stale),
    }
#endregion
