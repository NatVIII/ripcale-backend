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
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.identity import content_hash, stable_id
from app.models import Event, PendingPost, Source, utcnow
from app.schema import ScrapedEvent, dump_images, load_images
from app.services import deepseek
from app.services.categories import exposed_category_names, normalize_proposed
from app.services.clock import now as clock_now
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


class Decision(BaseModel):
    action: Literal["create", "modify", "ignore"]
    event: EventFields | None = None
    match_id: str | None = None
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
    "community calendar, and whether it is new or an update/reschedule of an "
    "existing event. Respond with JSON only."
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


def current_events(source_id: int, limit: int) -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(
            select(Event)
            .where(Event.source_id == source_id, Event.archived_at.is_(None))
            .order_by(Event.start_at.desc())
            .limit(limit)
        ).all()
    return [
        {
            "id": e.id,
            "title": e.title,
            "start_at": e.start_at.isoformat() if e.start_at else None,
            "location": e.location,
        }
        for e in rows
    ]
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
def decide(transcription: str, caption: str | None, events: list[dict], context: str | None = None, published_at: datetime | None = None) -> Decision:
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
    user = (
        f"{context_block}"
        f"Today's date is {local_datetime(now)}.\n"
        f"{pub_line}\n"
        f"Transcript of the post:\n---\n{transcription or ''}\n---\n\n"
        f"Caption:\n{caption or ''}\n"
        "---\n\nThe source's current events (id | title | start_at | location):\n"
        f"{json.dumps(events, ensure_ascii=False, indent=2)}\n\n"
        "Decide: is this an event? If yes, is it a NEW event or an "
        "update/reschedule of an existing one? Output JSON with keys: "
        "'action' ('create'|'modify'|'ignore'), 'event' ({title, description, "
        "location, start_at, end_at, timezone, all_day, categories}), 'match_id' "
        "(existing event id, only for 'modify'), 'reason' (short).\n"
        f"Categories: choose ONLY from this list (or leave empty): "
        f"{', '.join(allowed) or '(none available)'}.\n"
        "Only emit dates/times/location that appear in the transcript, caption, "
        "or source context; leave them null if not stated anywhere. When the "
        "caption uses relative dates ('next Monday', 'this week', 'TONIGHT', "
        "'tomorrow'), interpret them relative to the post's publish date, not "
        "today. start_at/end_at in ISO 8601 with a timezone offset (or Z for UTC)."
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
def apply_decision(session: Session, post: PendingPost, decision: Decision) -> None:
    source = session.get(Source, post.source_id)
    default_names = [c for c in (source.default_categories or "").split(",") if c.strip()] if source else []
    categories = normalize_proposed(default_names + (decision.event.categories if decision.event else []))

    if decision.action == "ignore":
        post.status = "ignored"
    elif decision.action in ("create", "modify") and decision.event is not None:
        f = decision.event
        scraped = ScrapedEvent(
            uid=post.uid,
            title=f.title,
            description=f.description,
            location=f.location,
            url=post.url,
            images=load_images(post.images),
            start_at=_parse_dt(f.start_at, f.timezone),
            end_at=_parse_dt(f.end_at, f.timezone),
            timezone=f.timezone,
            all_day=f.all_day,
            categories=categories,
        )
        event = (
            session.get(Event, decision.match_id)
            if decision.action == "modify" and decision.match_id
            else None
        )
        if event is None:
            event = Event(
                id=stable_id(source.name if source else "", scraped),
                source_id=post.source_id,
                uid=post.uid,
                title=f.title,
                description=f.description,
                location=f.location,
                url=post.url,
                images=dump_images(load_images(post.images)),
                start_at=_parse_dt(f.start_at, f.timezone),
                end_at=_parse_dt(f.end_at, f.timezone),
                timezone=f.timezone,
                all_day=f.all_day,
                categories=",".join(categories),
                content_hash=content_hash(scraped),
                last_seen_at=clock_now(),
                pinned=True,
            )
            session.add(event)
            post.status = "created"
        else:
            event.title = f.title
            event.description = f.description
            event.location = f.location
            event.url = post.url
            event.images = dump_images(load_images(post.images))
            event.start_at = _parse_dt(f.start_at, f.timezone)
            event.end_at = _parse_dt(f.end_at, f.timezone)
            event.timezone = f.timezone
            event.all_day = f.all_day
            event.categories = ",".join(categories)
            event.content_hash = content_hash(scraped)
            event.pinned = True
            event.updated_at = utcnow()
            post.status = "modified"
        post.match_event_id = event.id
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
            "context": source.llm_context if source else None,
            "published_at": post.published_at,
        }
        session.commit()

    # 2. slow LLM calls (no DB session held)
    try:
        transcription = snapshot["transcription"]
        if transcription is None:
            transcription = transcribe(snapshot["images"], snapshot["caption"])
        events = current_events(snapshot["source_id"], settings.llm_context_events)
        decision = decide(transcription, snapshot["caption"], events, context=snapshot["context"], published_at=snapshot["published_at"])
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
