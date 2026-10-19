"""Overseer duplicate/conflict detection (F67.01).

Cross-source dedup: find pairs of events that are (a) from different sources,
(b) time-proximate, and (c) title-similar — candidates for "the same real-world
event listed on two calendars". The LLM decision (F67.02) and the elevate/redirect
apply (F67.03) are layered on top of these candidates.

`completeness_score()` ranks how much detail an event carries (used to seed the
LLM's "which listing has the most information" call).
"""
#region: imports
import json
import re
from datetime import timedelta
from difflib import SequenceMatcher

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models import Approval, Event, utcnow
from app.schema import load_images
from app.services import approvals, deepseek
from app.services.clock import now as clock_now
from app.services.events import update_event
#endregion


#region: constants
_PROXIMITY = timedelta(hours=12)  # events starting within this window are "the same time"
#endregion


#region: title similarity
def _normalize_title(title: str | None) -> str:
    t = (title or "").lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def title_similarity(title_a: str | None, title_b: str | None) -> float:
    """0.0–1.0 similarity of two titles (normalized + fuzzy)."""
    a = _normalize_title(title_a)
    b = _normalize_title(title_b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()
#endregion


#region: completeness score
def completeness_score(event: Event) -> float:
    """Heuristic for "how much detail does this listing carry" (higher = richer)."""
    score = 0.0
    if event.location:
        score += 1.0
    if event.url:
        score += 1.0
    if event.end_at is not None:
        score += 0.5
    if event.description:
        score += min(len(event.description) / 100.0, 1.0)
    score += min(len(load_images(event.images)), 4) * 0.25
    return score
#endregion


#region: candidate pairs
def find_candidate_pairs(
    session: Session,
    *,
    window_days: int = 14,
    similarity_threshold: float = 0.5,
) -> list[tuple[Event, Event]]:
    """Return cross-source, time-proximate, title-similar event pairs.

    Only live, non-placeholder, non-redirected events starting between now and
    `window_days` ahead are considered. Pairs are ordered by earliest start.
    """
    now = clock_now()
    horizon = now + timedelta(days=window_days)
    rows = session.exec(
        select(Event)
        .where(
            Event.archived_at.is_(None),
            Event.redirect_to_id.is_(None),
            Event.placeholder == False,  # noqa: E712
            Event.start_at.is_not(None),
            Event.start_at >= now,
            Event.start_at <= horizon,
        )
        .order_by(Event.start_at)
    ).all()

    pairs: list[tuple[Event, Event]] = []
    for i in range(len(rows)):
        a = rows[i]
        for j in range(i + 1, len(rows)):
            b = rows[j]
            if a.source_id == b.source_id:
                continue
            if b.start_at - a.start_at > _PROXIMITY:
                break  # rows are time-sorted; no later event can be proximate
            if title_similarity(a.title, b.title) < similarity_threshold:
                continue
            pairs.append((a, b))
    return pairs
#endregion


#region: pairwise decision (F67.02)
_DECIDE_MAX_TOKENS = 500
_ENRICHABLE_FIELDS = {"title", "description", "location", "url", "timezone"}

_DECIDE_PAIR = (
    "Two events may be the same real-world event listed on two different "
    "calendars. Decide whether they are duplicates, and if so which listing is "
    "more complete/authoritative (the 'canonical' one). Respond with JSON only."
)


class PairDecision(BaseModel):
    same: bool
    canonical_id: str | None = None
    enrich: dict[str, str] = Field(default_factory=dict)
    reason: str = ""


def _snapshot(event: Event, score: float, source_names: dict[int, str] | None) -> dict:
    return {
        "id": event.id,
        "source": (source_names or {}).get(event.source_id, str(event.source_id)),
        "title": event.title,
        "description": event.description,
        "location": event.location,
        "url": event.url,
        "start_at": event.start_at.isoformat() if event.start_at else None,
        "end_at": event.end_at.isoformat() if event.end_at else None,
        "timezone": event.timezone,
        "all_day": event.all_day,
        "categories": event.categories,
        "completeness": round(score, 2),
    }


def _validate_decision(decision: PairDecision, a: Event, b: Event) -> PairDecision:
    """Coerce an LLM answer into a valid decision (winner ∈ {a, b}, enrich keys only)."""
    if decision.same:
        if decision.canonical_id not in (a.id, b.id):
            decision.canonical_id = a.id if completeness_score(a) >= completeness_score(b) else b.id
        decision.enrich = {k: v for k, v in decision.enrich.items() if k in _ENRICHABLE_FIELDS}
    else:
        decision.canonical_id = None
        decision.enrich = {}
    return decision


def decide_pair(event_a: Event, event_b: Event, source_names: dict[int, str] | None = None) -> PairDecision:
    """Ask DeepSeek whether two events are duplicates and which is canonical."""
    user = (
        f"Event A:\n{json.dumps(_snapshot(event_a, completeness_score(event_a), source_names), ensure_ascii=False, indent=2)}\n\n"
        f"Event B:\n{json.dumps(_snapshot(event_b, completeness_score(event_b), source_names), ensure_ascii=False, indent=2)}\n\n"
        "Respond with JSON: {'same': bool, 'canonical_id': '<event id>' (only when "
        "same), 'enrich': {<field>: <string value>} (fields to copy from the loser "
        "onto the winner, only when the winner is MISSING that info and the loser "
        "has it), 'reason': short}. Enrichable fields: title, description, location, "
        "url, timezone."
    )
    raw = deepseek.chat(
        [{"role": "system", "content": _DECIDE_PAIR}, {"role": "user", "content": user}],
        json_mode=True,
        thinking=False,
        max_tokens=_DECIDE_MAX_TOKENS,
    )
    return _validate_decision(PairDecision.model_validate_json(raw), event_a, event_b)
#endregion


#region: elevate / redirect (F67.03)
def _is_missing(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def propose_merge(session: Session, winner: Event, loser: Event, enrich: dict, reason: str) -> bool:
    """Create an `event_merge` approval proposal (skip if one is already pending)."""
    for row in session.exec(
        select(Approval).where(Approval.kind == "event_merge", Approval.status == "pending")
    ).all():
        try:
            payload = json.loads(row.payload)
        except (json.JSONDecodeError, TypeError):
            continue
        if payload.get("canonical_id") == winner.id and payload.get("loser_id") == loser.id:
            return False
    approvals.create_in_session(
        session, "event_merge", source_name="",
        payload={"canonical_id": winner.id, "loser_id": loser.id, "enrich": enrich},
        reason=reason,
    )
    return True


def _apply_event_merge(session: Session, approval: Approval) -> None:
    """Approval applier: enrich + pin the winner, redirect the loser to it."""
    try:
        payload = json.loads(approval.payload)
    except (json.JSONDecodeError, TypeError):
        return
    winner = session.get(Event, payload.get("canonical_id"))
    loser = session.get(Event, payload.get("loser_id"))
    if winner is None or loser is None:
        raise RuntimeError("event_merge: canonical/loser event not found")

    enrich = payload.get("enrich") or {}
    fields = {
        k: v for k, v in enrich.items()
        if k in _ENRICHABLE_FIELDS and _is_missing(getattr(winner, k, None))
    }
    if fields:
        update_event(session, winner.id, fields, pinned=True)
    else:
        winner.pinned = True
        winner.updated_at = utcnow()

    loser.redirect_to_id = winner.id
    loser.updated_at = utcnow()


approvals.register("event_merge", _apply_event_merge)
#endregion
