"""Declarative recurring placeholders (F66.02).

Turns each `SourceConfig.recurrences` declaration into a pinned, recurring
placeholder `Event` (master, carrying `rrule`) and archives any placeholder
master (plus its occurrence overrides) whose declaration was removed — so
"nixing the line" nixes the series. The master's identity is a synthetic `uid`
derived from source + title + rrule + start_at, making materialization
idempotent and removals discoverable.
"""
#region: imports
import hashlib
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel import Session, select

from app.identity import content_hash, stable_id
from app.intake import load as load_intake, save as save_intake
from app.models import Event, Source, utcnow
from app.schema import RecurrenceConfig, ScrapedEvent, SourceConfig
from app.services import approvals
from app.services.clock import now as clock_now
from app.services.recurrence import normalize_rrule
from app.timeutil import to_utc_naive
#endregion


logger = logging.getLogger(__name__)


#region: identity + parsing
def _series_uid(source_name: str, decl: RecurrenceConfig) -> str:
    key = f"{source_name}:{decl.title}:{decl.rrule}:{decl.start_at}"
    return "recurrence:" + hashlib.sha256(key.encode()).hexdigest()


def _parse_start(value: str, tz: str | None) -> datetime | None:
    """Parse an ISO start (offset/Z, or naive + IANA tz) into naive UTC."""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None and tz:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(tz))
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return to_utc_naive(dt)
#endregion


#region: materialization
def materialize(session: Session, source: Source, cfg: SourceConfig) -> dict:
    """Upsert placeholder masters from `cfg.recurrences`; archive removed ones."""
    now = clock_now()
    kept_uids: set[str] = set()
    created = updated = 0

    for decl in cfg.recurrences:
        try:
            uid = _series_uid(cfg.name, decl)
            kept_uids.add(uid)
            start_at = _parse_start(decl.start_at, decl.timezone)
            rrule = normalize_rrule(decl.rrule, decl.timezone)
            scraped = ScrapedEvent(
                uid=uid,
                title=decl.title,
                description=decl.description,
                location=decl.location,
                timezone=decl.timezone,
                start_at=start_at,
                rrule=rrule,
            )
        except Exception:  # noqa: BLE001 — skip a bad declaration, keep going
            logger.warning("placeholder declaration invalid: %r", decl.title)
            continue

        event_id = stable_id(cfg.name, scraped)
        existing = session.get(Event, event_id)
        if existing is None:
            session.add(
                Event(
                    id=event_id,
                    source_id=source.id,
                    uid=uid,
                    title=decl.title,
                    description=decl.description,
                    location=decl.location,
                    timezone=decl.timezone,
                    start_at=start_at,
                    rrule=rrule,
                    content_hash=content_hash(scraped),
                    last_seen_at=now,
                    pinned=True,
                    placeholder=True,
                )
            )
            created += 1
        else:
            existing.title = decl.title
            existing.description = decl.description
            existing.location = decl.location
            existing.timezone = decl.timezone
            existing.start_at = start_at
            existing.rrule = rrule
            existing.content_hash = content_hash(scraped)
            existing.last_seen_at = now
            existing.pinned = True
            existing.placeholder = True
            existing.archived_at = None  # re-declared → un-archive
            existing.archived_reason = None
            existing.updated_at = utcnow()
            updated += 1

    archived = 0
    masters = session.exec(
        select(Event).where(
            Event.source_id == source.id,
            Event.placeholder == True,  # noqa: E712
            Event.archived_at.is_(None),
        )
    ).all()
    for master in masters:
        if master.uid in kept_uids:
            continue
        master.archived_at = now
        master.archived_reason = "removed"
        master.updated_at = utcnow()
        archived += 1
        # also archive occurrence overrides that share this master's uid
        for override in session.exec(
            select(Event).where(
                Event.source_id == source.id,
                Event.uid == master.uid,
                Event.recurrence_id.is_not(None),
                Event.archived_at.is_(None),
            )
        ).all():
            override.archived_at = now
            override.archived_reason = "removed"
            override.updated_at = utcnow()
            archived += 1

    return {"created": created, "updated": updated, "archived": archived}
#endregion


#region: approval appliers (F66.03)
def _source_config(intake, name: str) -> SourceConfig | None:
    return next((s for s in intake.sources if s.name == name), None)


def _find_or_create_source(session: Session, cfg: SourceConfig) -> Source:
    source = session.exec(select(Source).where(Source.name == cfg.name)).first()
    if source is not None:
        return source
    source = Source(
        name=cfg.name,
        url=cfg.url,
        gatherer=cfg.gatherer,
        is_public=cfg.is_public,
        default_categories=",".join(cfg.default_categories),
        llm_context=cfg.llm_context,
    )
    session.add(source)
    session.flush()
    session.refresh(source)
    return source


def _apply_add_recurrence(session: Session, approval) -> None:
    try:
        decl = RecurrenceConfig(**json.loads(approval.payload))
    except (json.JSONDecodeError, TypeError, ValueError):
        return  # malformed proposal — no-op
    intake = load_intake()
    cfg = _source_config(intake, approval.source_name)
    if cfg is None:
        raise RuntimeError(f"source not found: {approval.source_name}")
    if any(d.title == decl.title and d.rrule == decl.rrule for d in cfg.recurrences):
        return  # already declared
    cfg.recurrences.append(decl)
    save_intake(intake)
    materialize(session, _find_or_create_source(session, cfg), cfg)


def _apply_remove_recurrence(session: Session, approval) -> None:
    try:
        title = (json.loads(approval.payload) or {}).get("title", "").strip()
    except (json.JSONDecodeError, TypeError, ValueError):
        title = ""
    if not title:
        return
    intake = load_intake()
    cfg = _source_config(intake, approval.source_name)
    if cfg is None:
        raise RuntimeError(f"source not found: {approval.source_name}")
    cfg.recurrences = [d for d in cfg.recurrences if d.title != title]
    save_intake(intake)
    materialize(session, _find_or_create_source(session, cfg), cfg)


approvals.register("recurrence_add", _apply_add_recurrence)
approvals.register("recurrence_remove", _apply_remove_recurrence)
#endregion
