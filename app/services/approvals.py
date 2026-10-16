"""Approval queue (F66): human-reviewed, LLM-proposed changes.

A generic, API-first queue so the same approve/reject loop can be driven by a
debug page today and a Telegram bot later. `create()` enqueues a proposal;
`approve()` marks it approved and dispatches to a kind-specific applier
(registered via `register()`); `reject()` marks it rejected.

Appliers run in the same transaction as the status change: if one raises, the
whole transaction rolls back and the approval stays `pending` (the error
propagates to the caller).
"""
#region: imports
import json
from typing import Callable
from uuid import uuid4

from sqlmodel import Session, select

from app.db import engine
from app.models import Approval, utcnow
#endregion


#region: statuses
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
#endregion


#region: apply registry
_appliers: dict[str, Callable[[Session, Approval], None]] = {}


def register(kind: str, applier: Callable[[Session, Approval], None]) -> None:
    """Register the apply function run when a `kind` proposal is approved."""
    _appliers[kind] = applier
#endregion


#region: serialize
def _parse_payload(raw: str):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def _row(a: Approval) -> dict:
    return {
        "id": a.id,
        "kind": a.kind,
        "source_name": a.source_name,
        "payload": _parse_payload(a.payload),
        "reason": a.reason,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
    }
#endregion


#region: queue
def create(kind: str, *, source_name: str = "", payload: dict | None = None, reason: str = "") -> str:
    """Enqueue a proposal and return its id."""
    approval_id = uuid4().hex
    approval = Approval(
        id=approval_id,
        kind=kind,
        source_name=source_name or "",
        payload=json.dumps(payload or {}),
        reason=reason or "",
        status=STATUS_PENDING,
    )
    with Session(engine) as session:
        session.add(approval)
        session.commit()
    return approval_id


def create_in_session(
    session: Session,
    kind: str,
    *,
    source_name: str = "",
    payload: dict | None = None,
    reason: str = "",
) -> Approval:
    """Add a pending proposal to `session` (no commit) — for callers already in a transaction."""
    approval = Approval(
        id=uuid4().hex,
        kind=kind,
        source_name=source_name or "",
        payload=json.dumps(payload or {}),
        reason=reason or "",
        status=STATUS_PENDING,
    )
    session.add(approval)
    return approval


def list_approvals(status: str | None = None) -> list[dict]:
    """List proposals (most recent first); `status=None` returns all."""
    with Session(engine) as session:
        stmt = select(Approval).order_by(Approval.created_at.desc())
        if status:
            stmt = stmt.where(Approval.status == status)
        rows = session.exec(stmt).all()
    return [_row(a) for a in rows]


def approve(approval_id: str) -> bool:
    """Approve a pending proposal; run its applier. Returns False if absent/not pending."""
    with Session(engine) as session:
        approval = session.get(Approval, approval_id)
        if approval is None or approval.status != STATUS_PENDING:
            return False
        approval.status = STATUS_APPROVED
        approval.resolved_at = utcnow()
        approval.updated_at = utcnow()
        applier = _appliers.get(approval.kind)
        if applier is not None:
            applier(session, approval)
        session.commit()
    return True


def reject(approval_id: str) -> bool:
    """Reject a pending proposal. Returns False if absent/not pending."""
    with Session(engine) as session:
        approval = session.get(Approval, approval_id)
        if approval is None or approval.status != STATUS_PENDING:
            return False
        approval.status = STATUS_REJECTED
        approval.resolved_at = utcnow()
        approval.updated_at = utcnow()
        session.commit()
    return True
#endregion
