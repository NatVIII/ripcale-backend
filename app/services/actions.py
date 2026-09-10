"""Request-agnostic admin operations.

The single source of truth for admin/debug operations. Both the JSON API
(`app/routers/api.py`) and the HTML debug pages call these functions, so the
logic never diverges. Functions take plain arguments and return plain data;
client errors raise `ActionError`.
"""
#region: imports
import secrets
import time

from sqlmodel import Session

from app.categorize import apply as categorize_service
from app.categorize import resolve_rules
from app.db import engine
from app.ingest import process_source, run_report
from app.intake import load as load_intake
from app.logging import LOG_TAIL_LINES, read_log_tail
from app.registry import load_gatherer, load_sources
from app.schema import CategoryRule, SourceConfig
from app.serializers import to_fullcalendar
from app.services import stats
from app.services.coherence import check as coherence_check
from app.services.events import DEFAULT_LIMIT, query_events, source_names
from app.services.retag import retag as retag_service
from app.services.status import gatherer_rollup, read_status, record_run, record_status
from app.services.testrunner import collect_tests, run_tests
from app.services.wipe import wipe_all
#endregion


#region: error
class ActionError(Exception):
    """A client error (bad input) — carries an HTTP status for the API layer."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status
#endregion


#region: read actions
def overview() -> dict:
    with Session(engine) as session:
        ov = stats.overview(session)
    ov["last_ingest"] = stats.read_last_ingest()
    return ov


def sources() -> list:
    with Session(engine) as session:
        return stats.sources(session)


def events(start=None, end=None, category=None, limit: int | None = DEFAULT_LIMIT) -> list:
    with Session(engine) as session:
        evs = query_events(session, start=start, end=end, category=category, limit=limit)
        names = source_names(session, evs)
    return [to_fullcalendar(e, names.get(e.source_id)) for e in evs]


def event(event_id: str) -> dict | None:
    with Session(engine) as session:
        return stats.event_dump(session, event_id)


def stale() -> list:
    with Session(engine) as session:
        return stats.stale_events(session)


def coherence() -> list:
    return coherence_check()


def logs(n: int = LOG_TAIL_LINES) -> str:
    return read_log_tail(n)


def status() -> dict:
    with Session(engine) as session:
        srcs = stats.sources(session)
    statuses = read_status()
    return {"sources": srcs, "statuses": statuses, "rollup": gatherer_rollup(srcs, statuses)}


def symlinks() -> dict:
    try:
        return load_intake().category_symlinks
    except Exception:  # noqa: BLE001 — a broken intake must not break the dashboard
        return {}
#endregion


#region: write actions
def ingest(dry_run: bool = True) -> dict:
    return {"dry_run": dry_run, "sources": run_report(dry_run=dry_run)}


def retag(from_cat: str, to_cat: str | None = None, dry_run: bool = True) -> dict:
    from_cat = (from_cat or "").strip()
    if not from_cat:
        raise ActionError("'from' is required")
    to_cat = (to_cat or "").strip() or None
    with Session(engine) as session:
        changed, preview = retag_service(session, from_cat, to_cat)
        if not dry_run:
            session.commit()
    return {
        "changed": changed,
        "dry_run": dry_run,
        "preview": [{"title": t, "before": b, "after": a} for t, b, a in preview],
    }


_WIPE_TTL = 60.0
_pending_wipes: dict[str, float] = {}


def wipe_begin() -> str:
    challenge = secrets.token_urlsafe(24)
    _pending_wipes[challenge] = time.time() + _WIPE_TTL
    return challenge


def wipe_confirm(challenge: str) -> dict:
    challenge = (challenge or "").strip()
    if not challenge:
        raise ActionError("challenge is required")
    deadline = _pending_wipes.get(challenge)
    if deadline is None or time.time() > deadline:
        _pending_wipes.pop(challenge, None)
        raise ActionError("invalid or expired challenge")
    result = wipe_all()
    _pending_wipes.pop(challenge, None)
    return result


def tests_list() -> list:
    return collect_tests()


def tests_run(test_id: str | None = None) -> dict:
    rc, output = run_tests(test_id)
    return {"exit": rc, "output": output}
#endregion


#region: pipeline actions
def gather(cfg: SourceConfig) -> dict:
    try:
        result = load_gatherer(cfg.gatherer)(cfg)
    except Exception as exc:
        record_status(cfg.name, "error", message=str(exc))
        raise
    record_run(cfg.name, len(result.events))
    return result.model_dump(mode="json")


def sieve(cfg: SourceConfig) -> dict:
    run_fn = load_gatherer(cfg.gatherer)
    try:
        with Session(engine) as session:
            sieved, _ = process_source(session, cfg, run_fn, dry_run=True)
    except Exception as exc:
        record_status(cfg.name, "error", message=str(exc))
        raise
    record_run(cfg.name, len(sieved.new) + len(sieved.updated) + sieved.unchanged)
    return sieved.model_dump(mode="json")


def decide(cfg: SourceConfig, dry_run: bool = True) -> dict:
    run_fn = load_gatherer(cfg.gatherer)
    try:
        with Session(engine) as session:
            sieved, report = process_source(session, cfg, run_fn, dry_run=dry_run)
            if not dry_run:
                session.commit()
    except Exception as exc:
        record_status(cfg.name, "error", message=str(exc))
        raise
    record_run(cfg.name, len(sieved.new) + len(sieved.updated) + sieved.unchanged)
    return {"dry_run": dry_run, "report": report, "sieved": sieved.model_dump(mode="json")}


def categorize(cfg: SourceConfig, rules: list[CategoryRule] | None, include_configured: bool = True, dry_run: bool = True) -> dict:
    if rules is None:
        resolved = None
    else:
        resolved = (resolve_rules(cfg) + rules) if include_configured else rules

    run_fn = load_gatherer(cfg.gatherer)
    try:
        if dry_run:
            result = run_fn(cfg)
            categorize_service(result.source, result.events, rules=resolved)
            events = [{"title": e.title, "categories": e.categories} for e in result.events]
            record_run(cfg.name, len(events))
            return {"dry_run": True, "events": events}
        with Session(engine) as session:
            sieved, report = process_source(session, cfg, run_fn, dry_run=False, rules=resolved)
            session.commit()
    except Exception as exc:
        record_status(cfg.name, "error", message=str(exc))
        raise
    record_run(cfg.name, len(sieved.new) + len(sieved.updated) + sieved.unchanged)
    return {"dry_run": False, "report": report, "sieved": sieved.model_dump(mode="json")}
#endregion


#region: parsing
def resolve_source_spec(data: dict) -> SourceConfig | None:
    """Build a SourceConfig from a spec (`source` name or manual fields)."""
    source_name = (data.get("source") or "").strip()
    if source_name and source_name != "manual":
        for cfg in load_sources():
            if cfg.name == source_name:
                return cfg
        return None
    name = (data.get("name") or "").strip() or "manual"
    gatherer = (data.get("gatherer") or "").strip()
    url = (data.get("url") or "").strip()
    if not gatherer or not url:
        return None
    return SourceConfig(name=name, gatherer=gatherer, url=url)


def parse_rules(data: dict) -> list[CategoryRule] | None:
    rules = data.get("rules")
    if rules is None:
        return None
    if isinstance(rules, dict):
        rules = [rules]
    return [CategoryRule(**r) for r in rules]
#endregion
