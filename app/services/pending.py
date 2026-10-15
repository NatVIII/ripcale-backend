"""Pending-post queue for LLM decide-before-insert sources (F65).

`enqueue()` is the enqueue stage: it hosts the gathered posts' images and upserts
them into `PendingPost` (new/changed → `pending`, unchanged → skipped). The
background worker (`app/services/llm_worker.py`) later resolves them.
"""
#region: imports
import logging
from datetime import timedelta

from sqlmodel import Session, select

from app.models import PendingPost, Source, utcnow
from app.schema import GathererResult, ImageRef, dump_images
from app.services.clock import now as clock_now
from app.services.images import host_images
#endregion


logger = logging.getLogger(__name__)

# statuses
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_CREATED = "created"
STATUS_MODIFIED = "modified"
STATUS_IGNORED = "ignored"
STATUS_FAILED = "failed"


def enqueue(session: Session, source: Source, result: GathererResult, *, dry_run: bool = False) -> dict:
    """Host images + upsert posts into the queue; return a summary."""
    host_images(session, result.events)

    inserted = changed = unchanged = 0
    for event in result.events:
        uid = event.uid
        if not uid:
            continue
        images = dump_images([ImageRef(url=img.url) for img in event.images])  # url-only: `source_url` is ephemeral (signed CDN) and churns
        caption = event.description or ""
        published_at = event.start_at  # gatherer start_at = post publish time for decide-before-insert sources (F65.02)

        existing = session.get(PendingPost, uid)
        if existing is None:
            if not dry_run:
                session.add(
                    PendingPost(
                        uid=uid,
                        source_id=source.id,
                        url=event.url,
                        caption=caption,
                        images=images,
                        published_at=published_at,
                        status=STATUS_PENDING,
                    )
                )
            inserted += 1
        elif existing.caption != caption or existing.images != images:
            if not dry_run:
                existing.caption = caption
                existing.images = images
                existing.url = event.url
                existing.published_at = published_at
                existing.status = STATUS_PENDING
                existing.transcription = None
                existing.decision = None
                existing.error = None
                existing.attempts = 0
                existing.updated_at = utcnow()
            changed += 1
        else:
            if not dry_run and existing.published_at is None and published_at is not None:
                existing.published_at = published_at  # backfill for pre-migration rows
            unchanged += 1

    if not dry_run:
        source.last_fetched_at = clock_now()
        session.add(source)

    return {"enqueued": inserted, "changed": changed, "unchanged": unchanged}


def reset_stale_processing(session: Session, timeout_seconds: int) -> int:
    """Reset `processing` posts stuck longer than the timeout back to `pending`."""
    cutoff = clock_now() - timedelta(seconds=timeout_seconds)
    rows = session.exec(
        select(PendingPost).where(
            PendingPost.status == STATUS_PROCESSING,
            PendingPost.updated_at < cutoff,
        )
    ).all()
    for post in rows:
        post.status = STATUS_PENDING
        post.updated_at = utcnow()
    return len(rows)


def list_pending(session: Session, limit: int = 100) -> list[dict]:
    """Return the queue (most-recent first) for observability."""
    names = {s.id: s.name for s in session.exec(select(Source)).all()}
    rows = session.exec(
        select(PendingPost).order_by(PendingPost.created_at.desc()).limit(limit)
    ).all()
    return [
        {
            "uid": p.uid,
            "source": names.get(p.source_id),
            "caption": (p.caption or "")[:120],
            "status": p.status,
            "attempts": p.attempts,
            "error": p.error,
            "transcription": (p.transcription or "")[:200] if p.transcription else None,
            "decision": p.decision,
            "match_event_id": p.match_event_id,
        }
        for p in rows
    ]
#endregion
