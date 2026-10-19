"""Pinned-event change conflicts (F68).

A pinned event whose source content changed surfaces as an `EventConflict`.
`resolve()` applies one of three actions: `ignore` (keep the pinned content),
`apply` (adopt the incoming source content wholesale), or `syncretize` (merge the
new facts into the pinned content with a cheap LLM).
"""
#region: imports
import json

from sqlmodel import Session, select

from app.db import engine
from app.identity import content_hash
from app.models import Event, EventConflict, utcnow
from app.schema import ScrapedEvent, dump_exdates, dump_images
from app.services import deepseek
from app.services.events import update_event
#endregion


#region: constants
_SYNCRETIZE_FIELDS = {"title", "description", "location", "url", "timezone"}
_SYNCRETIZE_MAX_TOKENS = 600

_SYNCRETIZE = (
    "A pinned calendar event's source has new information. Merge the new facts "
    "into the pinned content, keeping the pinned content authoritative for "
    "anything the source doesn't clearly change. Respond with JSON only."
)
#endregion


#region: serialize
def _parse(raw):
    try:
        return json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        return raw


def _parse_list(raw):
    try:
        return json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        return []


def _row(c: EventConflict) -> dict:
    return {
        "id": c.id,
        "event_id": c.event_id,
        "incoming": _parse(c.incoming),
        "changed_fields": _parse_list(c.changed_fields),
        "status": c.status,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
    }
#endregion


#region: list + resolve
def list_conflicts(status: str | None = None) -> list[dict]:
    with Session(engine) as session:
        stmt = select(EventConflict).order_by(EventConflict.created_at.desc())
        if status:
            stmt = stmt.where(EventConflict.status == status)
        rows = session.exec(stmt).all()
    return [_row(c) for c in rows]


def resolve(conflict_id: str, action: str) -> bool:
    """Resolve a pending conflict via `ignore` / `apply` / `syncretize`."""
    if action not in ("ignore", "apply", "syncretize"):
        return False
    with Session(engine) as session:
        conflict = session.get(EventConflict, conflict_id)
        if conflict is None or conflict.status != "pending":
            return False
        if action == "ignore":
            conflict.status = "ignored"
        elif action == "apply":
            _apply(session, conflict)
            conflict.status = "applied"
        else:
            _syncretize(session, conflict)
            conflict.status = "merged"
        conflict.resolved_at = utcnow()
        conflict.updated_at = utcnow()
        session.commit()
    return True
#endregion


#region: apply / syncretize
def _write_incoming(event: Event, incoming: ScrapedEvent) -> None:
    event.title = incoming.title
    event.description = incoming.description
    event.location = incoming.location
    event.url = incoming.url
    event.images = dump_images(incoming.images)
    event.start_at = incoming.start_at
    event.end_at = incoming.end_at
    event.timezone = incoming.timezone
    event.all_day = incoming.all_day
    event.rrule = incoming.rrule
    event.recurrence_id = incoming.recurrence_id
    event.exdates = dump_exdates(incoming.exdates)
    event.categories = ",".join(sorted(set(incoming.categories)))
    event.content_hash = content_hash(incoming)
    event.pinned = True
    event.updated_at = utcnow()


def _apply(session: Session, conflict: EventConflict) -> None:
    event = session.get(Event, conflict.event_id)
    if event is None:
        return
    _write_incoming(event, ScrapedEvent(**json.loads(conflict.incoming)))


def _event_dict(x) -> dict:
    return {
        "title": x.title,
        "description": x.description,
        "location": x.location,
        "url": x.url,
        "start_at": x.start_at.isoformat() if x.start_at else None,
        "end_at": x.end_at.isoformat() if x.end_at else None,
        "timezone": x.timezone,
    }


def _syncretize(session: Session, conflict: EventConflict) -> None:
    event = session.get(Event, conflict.event_id)
    if event is None:
        return
    incoming = ScrapedEvent(**json.loads(conflict.incoming))
    changed = _parse_list(conflict.changed_fields)

    user = (
        "Pinned event (current):\n"
        f"{json.dumps(_event_dict(event), ensure_ascii=False, indent=2)}\n\n"
        "New source content:\n"
        f"{json.dumps(_event_dict(incoming), ensure_ascii=False, indent=2)}\n\n"
        f"Changed fields: {', '.join(changed) or '(none)'}\n\n"
        "Respond with JSON: {<field>: <value>} — only the fields to update on the "
        "pinned event. Allowed fields: title, description, location, url, timezone."
    )
    raw = deepseek.chat(
        [{"role": "system", "content": _SYNCRETIZE}, {"role": "user", "content": user}],
        json_mode=True,
        thinking=False,
        max_tokens=_SYNCRETIZE_MAX_TOKENS,
    )
    try:
        merged = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(merged, dict):
        return
    fields = {k: v for k, v in merged.items() if k in _SYNCRETIZE_FIELDS and isinstance(v, str)}
    if fields:
        update_event(session, event.id, fields, pinned=True)
#endregion
