"""LLM event pipeline: transcription + decision + apply (F65).

Stage A transcribes an Instagram post's flyer image(s) + caption into text with
`deepseek-flash` (vision, non-thinking). Stage B feeds that text, plus the
source's current events, to `deepseek-flash` (JSON mode) and decides `create` /
`modify` / `ignore`. `process_one()` runs both stages, handles retry semantics,
and applies the decision. Categories are constrained to the publicly-exposed set.
"""
#region: imports
import base64
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.identity import content_hash, stable_id
from app.intake import load as load_intake
from app.models import Event, PendingPost, Source, utcnow
from app.schema import RecurrenceConfig, ScrapedEvent, dump_exdates, dump_images, load_exdates, load_images
from app.services import approvals, deepseek
from app.services.categories import exposed_category_names, normalize_proposed
from app.services.clock import now as clock_now
from app.services.recurrence import normalize_rrule, occurrences
from app.timeutil import local_datetime, to_utc_naive
#endregion


#region: limits
_TRANSCRIBE_MAX_TOKENS = 2000
_DECIDE_MAX_TOKENS = 800
#endregion


#region: decision model
class EventFields(BaseModel):
    title: str
    description: str | None = None
    location: str | None = None
    start_at: str | None = None   # ISO 8601 (with offset or Z)
    end_at: str | None = None
    timezone: str | None = None   # IANA zone
    all_day: bool = False
    categories: list[str] = Field(default_factory=list)

    @field_validator("all_day", mode="before")
    @classmethod
    def _all_day_null(cls, v):
        return False if v is None else v

    @field_validator("categories", mode="before")
    @classmethod
    def _categories_null(cls, v):
        return [] if v is None else v


class RecurrenceFields(BaseModel):
    """The declarative series the LLM proposes to add/remove (F66)."""

    title: str
    rrule: str | None = None
    start_at: str | None = None
    timezone: str | None = None
    location: str | None = None
    description: str | None = None


class Decision(BaseModel):
    action: Literal["create", "modify", "delete", "ignore", "add_recurrence", "remove_recurrence"]
    event: EventFields | None = None          # create/modify
    recurrence: RecurrenceFields | None = None  # add_recurrence / remove_recurrence
    match_id: str | None = None               # modify/delete: existing event id
    recurrence_id: str | None = None          # ISO DTSTART of the occurrence to override/cancel
    reason: str = ""
#endregion


#region: prompts
_TRANSCRIBE = (
    "Transcribe every piece of text visible in this image as faithfully as "
    "possible, preserving line structure, dates, times, locations, prices, URLs "
    "and handles. Output only the transcription text."
)

_DECIDE_SYSTEM = (
    "You decide whether an Instagram post represents a real-world event for a "
    "community calendar, and whether it is new, an update/reschedule, a "
    "cancellation, or evidence of a recurring schedule. Respond with JSON only."
)
#endregion


#region: helpers
def _image_block(url: str) -> dict | None:
    if url.startswith("/images/"):
        path = Path(settings.data_dir) / "images" / url.removeprefix("/images/")
        if path.is_file():
            ext = path.suffix.lstrip(".").lower()
            mime = {
                "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "webp": "image/webp", "gif": "image/gif",
            }.get(ext, "image/jpeg")
            b64 = base64.b64encode(path.read_bytes()).decode()
            return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        return None  # local file gone — skip it
    return {"type": "image_url", "image_url": {"url": url}}


def _parse_dt(value: str | None, tz_name: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None and tz_name:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(tz_name))
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return to_utc_naive(dt)


def current_events(source_id: int, limit: int, since: datetime | None = None) -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(
            select(Event)
            .where(Event.source_id == source_id, Event.archived_at.is_(None))
            .order_by(Event.start_at.desc())
            .limit(limit)
        ).all()
    since = since or (clock_now() - timedelta(days=7))
    result: list[dict] = []
    for e in rows:
        item = {
            "id": e.id,
            "title": e.title,
            "start_at": e.start_at.isoformat() if e.start_at else None,
            "location": e.location,
            "rrule": e.rrule,
            "recurrence_id": e.recurrence_id.isoformat() if e.recurrence_id else None,
            "placeholder": e.placeholder,
        }
        if e.rrule and e.start_at:
            occs = occurrences(e.rrule, e.start_at, e.timezone, count=6, since=since)
            item["occurrences"] = [o.isoformat() + "Z" for o in occs]
        result.append(item)
    return result


def current_recurrences(source_name: str) -> list[dict]:
    """The source's declared recurring-placeholder series (from intake.yaml)."""
    for cfg in load_intake().sources:
        if cfg.name == source_name:
            return [r.model_dump() for r in cfg.recurrences]
    return []
#endregion


#region: stage A — transcription
def transcribe(images: list[str], caption: str | None) -> str:
    content: list[dict] = [{"type": "text", "text": _TRANSCRIBE}]
    for url in images[: settings.llm_max_images]:
        block = _image_block(url)
        if block is not None:
            content.append(block)
    if caption:
        content[0]["text"] += f"\n\nCaption (for context): {caption}"
    return deepseek.chat(
        [{"role": "user", "content": content}],
        thinking=False,
        max_tokens=_TRANSCRIBE_MAX_TOKENS,
    )
#endregion


#region: stage B — decision
def decide(
    transcription: str,
    caption: str | None,
    events: list[dict],
    context: str | None = None,
    published_at: datetime | None = None,
    recurrences: list[dict] | None = None,
) -> Decision:
    allowed = exposed_category_names()
    now = clock_now()
    context_block = (
        f"Source context (standing guidance — follow unless the post says otherwise):\n{context}\n\n"
        if context
        else ""
    )
    pub_line = (
        f"This post was published on {local_datetime(published_at)}.\n"
        if published_at
        else "This post's publish time is unknown.\n"
    )
    recurrences_block = (
        "The source's declared recurring series (title | rrule | start_at | timezone):\n"
        f"{json.dumps(recurrences or [], ensure_ascii=False, indent=2)}\n\n"
    )
    user = (
        f"{context_block}"
        f"Today's date is {local_datetime(now)}.\n"
        f"{pub_line}\n"
        f"Transcript of the post:\n---\n{transcription or ''}\n---\n\n"
        f"Caption:\n{caption or ''}\n"
        "---\n\nThe source's current events (id | title | start_at | location | rrule | recurrence_id | placeholder | occurrences):\n"
        f"{json.dumps(events, ensure_ascii=False, indent=2)}\n\n"
        f"{recurrences_block}"
        "Decide the post's calendar effect and output JSON with exactly these keys: "
        "'action', 'event', 'recurrence', 'match_id', 'recurrence_id', 'reason'.\n"
        "Actions:\n"
        "- 'create': a NEW one-off event (no existing match). Set 'event'.\n"
        "- 'modify': update/reschedule an existing event (set 'match_id' to its id and 'event' to the new fields); OR fill in one occurrence of a recurring series (set 'match_id' to the master's id, 'recurrence_id' COPIED VERBATIM from that series' 'occurrences' list — choose the occurrence whose date matches the post's stated date, and 'event' to the real details).\n"
        "- 'delete': cancel an event (set 'match_id') or cancel one occurrence of a series (set 'match_id' to the master and 'recurrence_id' COPIED VERBATIM from its 'occurrences' list, choosing the occurrence matching the post's date).\n"
        "- 'add_recurrence': the post establishes a repeating schedule; propose a series via 'recurrence' ({title, rrule, start_at, timezone, location?, description?}). Only propose when the schedule is stated (in the post or source context).\n"
        "- 'remove_recurrence': the schedule is over/no longer consistent; remove a declared series via 'recurrence' ({title} matching the declaration to nix).\n"
        "- 'ignore': not an event.\n"
        "'event' fields: {title, description, location, start_at, end_at, timezone, all_day, categories}. "
        "Use the post's own title for 'event.title' — do not prefix the recurring series title. "
        "'recurrence' uses an RFC 5545 RRULE value (e.g. 'FREQ=WEEKLY;BYDAY=MO'), with start_at as the first occurrence.\n"
        f"Categories: choose ONLY from this list (or leave empty): "
        f"{', '.join(allowed) or '(none available)'}.\n"
        "Only emit dates/times/location that appear in the transcript, caption, "
        "or source context; leave them null if not stated anywhere. When the "
        "caption uses relative dates ('next Monday', 'this week', 'TONIGHT', "
        "'tomorrow'), interpret them relative to the post's publish date, not "
        "today. start_at/end_at in ISO 8601 with a timezone offset (or Z). "
        "recurrence_id must be COPIED VERBATIM from the target series' "
        "'occurrences' list — never computed by you."
    )
    raw = deepseek.chat(
        [{"role": "system", "content": _DECIDE_SYSTEM}, {"role": "user", "content": user}],
        json_mode=True,
        thinking=False,
        max_tokens=_DECIDE_MAX_TOKENS,
    )
    return Decision.model_validate_json(raw)
#endregion


#region: apply
def _scraped(post: PendingPost, f: EventFields, categories: list[str], *, uid: str, recurrence_id: datetime | None = None) -> ScrapedEvent:
    return ScrapedEvent(
        uid=uid,
        title=f.title,
        description=f.description,
        location=f.location,
        url=post.url,
        images=load_images(post.images),
        start_at=_parse_dt(f.start_at, f.timezone),
        end_at=_parse_dt(f.end_at, f.timezone),
        timezone=f.timezone,
        all_day=f.all_day,
        recurrence_id=recurrence_id,
        categories=categories,
    )


def _event_from_scraped(post: PendingPost, source_name: str, scraped: ScrapedEvent, categories: list[str]) -> Event:
    return Event(
        id=stable_id(source_name, scraped),
        source_id=post.source_id,
        uid=scraped.uid,
        title=scraped.title,
        description=scraped.description,
        location=scraped.location,
        url=scraped.url,
        images=dump_images(scraped.images),
        start_at=scraped.start_at,
        end_at=scraped.end_at,
        timezone=scraped.timezone,
        all_day=scraped.all_day,
        rrule=scraped.rrule,
        recurrence_id=scraped.recurrence_id,
        exdates=dump_exdates(scraped.exdates),
        categories=",".join(categories),
        content_hash=content_hash(scraped),
        last_seen_at=clock_now(),
        pinned=True,
    )


def _is_occurrence(master: Event, rid: datetime) -> bool:
    """True when `rid` is an actual DTSTART of the recurring master (F66.03)."""
    if not master.rrule or master.start_at is None:
        return True  # no recurrence to check against
    return rid in occurrences(master.rrule, master.start_at, master.timezone, count=400)


def _overwrite(event: Event, scraped: ScrapedEvent, categories: list[str]) -> None:
    event.title = scraped.title
    event.description = scraped.description
    event.location = scraped.location
    event.url = scraped.url
    event.images = dump_images(scraped.images)
    event.start_at = scraped.start_at
    event.end_at = scraped.end_at
    event.timezone = scraped.timezone
    event.all_day = scraped.all_day
    if scraped.rrule is not None:  # preserve recurrence when not restated
        event.rrule = scraped.rrule
    if scraped.recurrence_id is not None:
        event.recurrence_id = scraped.recurrence_id
    event.categories = ",".join(categories)
    event.content_hash = content_hash(scraped)
    event.pinned = True
    event.updated_at = utcnow()


def _apply_create_modify(session: Session, post: PendingPost, source_name: str, default_names: list[str], decision: Decision) -> None:
    f = decision.event
    categories = normalize_proposed(default_names + (f.categories or []))
    rid = _parse_dt(decision.recurrence_id, f.timezone)

    # occurrence override: fill in one occurrence of a recurring master
    master = session.get(Event, decision.match_id) if decision.match_id else None
    if master is not None and rid is not None:
        if not _is_occurrence(master, rid):
            post.status = "failed"
            post.error = "modify: recurrence_id is not an occurrence of the series"
            return
        scraped = _scraped(post, f, categories, uid=master.uid, recurrence_id=rid)
        override_id = stable_id(source_name, scraped)
        override = session.get(Event, override_id)
        if override is None:
            session.add(_event_from_scraped(post, source_name, scraped, categories))
        else:
            _overwrite(override, scraped, categories)
        post.match_event_id = override_id
        post.status = "modified"
        return

    # normal modify of a matched (non-recurring) event
    if decision.action == "modify" and decision.match_id:
        existing = session.get(Event, decision.match_id)
        if existing is not None:
            if existing.rrule is not None:
                post.status = "failed"
                post.error = "modify: match_id is a recurring series — use recurrence_id"
                return
            scraped = _scraped(post, f, categories, uid=existing.uid)
            _overwrite(existing, scraped, categories)
            post.match_event_id = existing.id
            post.status = "modified"
            return

    # create a new event keyed by the post (idempotent: overwrite on re-process)
    scraped = _scraped(post, f, categories, uid=post.uid)
    event_id = stable_id(source_name, scraped)
    existing = session.get(Event, event_id)
    if existing is None:
        session.add(_event_from_scraped(post, source_name, scraped, categories))
    else:
        _overwrite(existing, scraped, categories)
    post.match_event_id = event_id
    post.status = "created"


def _apply_delete(session: Session, post: PendingPost, decision: Decision) -> None:
    event = session.get(Event, decision.match_id) if decision.match_id else None
    if event is None:
        post.status = "failed"
        post.error = "delete: match_id not found"
        return
    rid = _parse_dt(decision.recurrence_id, event.timezone)
    if rid is not None:
        if not _is_occurrence(event, rid):
            post.status = "failed"
            post.error = "delete: recurrence_id is not an occurrence of the series"
            return
        exdates = load_exdates(event.exdates)
        if rid not in exdates:
            exdates.append(rid)
        event.exdates = dump_exdates(exdates)
    else:
        event.archived_at = clock_now()
        event.archived_reason = "cancelled"
    event.updated_at = utcnow()
    post.match_event_id = event.id
    post.status = "deleted"


def _apply_recurrence(session: Session, post: PendingPost, source_name: str, decision: Decision) -> None:
    rec = decision.recurrence
    if rec is None or not (rec.title or "").strip():
        post.status = "failed"
        post.error = f"{decision.action}: recurrence is required"
        return

    if decision.action == "add_recurrence":
        if not rec.rrule or not rec.start_at:
            post.status = "failed"
            post.error = "add_recurrence: rrule and start_at are required"
            return
        try:
            rrulestr(normalize_rrule(rec.rrule, rec.timezone))
        except Exception:  # noqa: BLE001 — reject unparseable rules
            post.status = "failed"
            post.error = "add_recurrence: invalid rrule"
            return
        if _parse_dt(rec.start_at, rec.timezone) is None:
            post.status = "failed"
            post.error = "add_recurrence: invalid start_at"
            return
        approvals.create_in_session(
            session, "recurrence_add",
            source_name=source_name, payload=rec.model_dump(), reason=decision.reason or "",
        )
    else:  # remove_recurrence
        approvals.create_in_session(
            session, "recurrence_remove",
            source_name=source_name, payload={"title": rec.title.strip()}, reason=decision.reason or "",
        )
    post.status = "proposed"


def apply_decision(session: Session, post: PendingPost, decision: Decision) -> None:
    source = session.get(Source, post.source_id)
    source_name = source.name if source else ""
    default_names = [c for c in (source.default_categories or "").split(",") if c.strip()] if source else []

    if decision.action == "ignore":
        post.status = "ignored"
    elif decision.action in ("add_recurrence", "remove_recurrence"):
        _apply_recurrence(session, post, source_name, decision)
    elif decision.action == "delete":
        _apply_delete(session, post, decision)
    elif decision.action in ("create", "modify") and decision.event is not None:
        _apply_create_modify(session, post, source_name, default_names, decision)
    else:
        post.status = "failed"
        post.error = f"decision had no event for action {decision.action!r}"

    post.processed_at = utcnow()
    post.updated_at = utcnow()
#endregion


#region: failure handling
def _transient_failure(uid: str, exc: Exception) -> None:
    with Session(engine) as session:
        post = session.get(PendingPost, uid)
        if post is None:
            return
        post.attempts += 1
        if post.attempts >= settings.llm_max_attempts:
            post.status = "failed"
            post.error = str(exc)
        else:
            post.status = "pending"  # retry next tick
        post.updated_at = utcnow()
        session.commit()


def _permanent_failure(uid: str, exc: Exception) -> None:
    with Session(engine) as session:
        post = session.get(PendingPost, uid)
        if post is None:
            return
        post.status = "failed"
        post.error = str(exc)
        post.updated_at = utcnow()
        session.commit()
#endregion


#region: worker unit
def process_one(uid: str) -> None:
    """Run Stage A + B + apply for one pending post (opens its own transactions)."""
    # 1. snapshot + mark processing
    with Session(engine) as session:
        post = session.get(PendingPost, uid)
        if post is None or post.status != "pending":
            return
        post.status = "processing"
        post.error = None
        post.updated_at = utcnow()
        source = session.get(Source, post.source_id)
        snapshot = {
            "images": [img.url for img in load_images(post.images)],
            "caption": post.caption,
            "transcription": post.transcription,
            "source_id": post.source_id,
            "source_name": source.name if source else "",
            "context": source.llm_context if source else None,
            "published_at": post.published_at,
        }
        session.commit()

    # 2. slow LLM calls (no DB session held)
    try:
        transcription = snapshot["transcription"]
        if transcription is None:
            transcription = transcribe(snapshot["images"], snapshot["caption"])
        events = current_events(
            snapshot["source_id"], settings.llm_context_events,
            since=(snapshot["published_at"] or clock_now()) - timedelta(days=7),
        )
        recurrences = current_recurrences(snapshot["source_name"])
        decision = decide(
            transcription, snapshot["caption"], events,
            context=snapshot["context"], published_at=snapshot["published_at"],
            recurrences=recurrences,
        )
    except deepseek.DeepSeekTransient as exc:
        _transient_failure(uid, exc)
        return
    except Exception as exc:  # noqa: BLE001 — permanent (bad key, malformed, bug)
        _permanent_failure(uid, exc)
        return

    # 3. apply
    with Session(engine) as session:
        post = session.get(PendingPost, uid)
        if post is None:
            return
        post.transcription = transcription
        post.decision = decision.model_dump_json()
        post.attempts = 0
        apply_decision(session, post, decision)
        session.commit()
#endregion
