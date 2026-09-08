"""Versioned JSON admin API (token + IP gated).

`register(app)` is called from `app/admin.py`. Every route is `/api/v1/...`,
guarded by `api_guard`, and returns a `{ok, data|error}` envelope. This is the
API-first surface for admin/debug interactivity — thin wrappers over services.
"""
#region: imports
import json
import logging
import secrets
import time
from datetime import datetime
from functools import wraps
from urllib.parse import unquote_plus

from robyn import Response, jsonify
from sqlmodel import Session

from app.categorize import apply as categorize, resolve_rules
from app.db import engine
from app.ingest import process_source, run_report
from app.logging import LOG_TAIL_LINES, read_log_tail
from app.registry import load_gatherer, load_sources
from app.schema import CategoryRule, SourceConfig
from app.security import api_guard
from app.serializers import to_fullcalendar
from app.services import stats
from app.services.coherence import check as coherence_check
from app.services.events import DEFAULT_LIMIT, query_events, source_names
from app.services.retag import retag
from app.services.testrunner import collect_tests, run_tests
from app.services.wipe import wipe_all
#endregion


VERSION = "v1"
logger = logging.getLogger(__name__)

_WIPE_TTL = 60.0
_pending_wipes: dict[str, float] = {}


#region: helpers
def _ok(data, status: int = 200) -> Response:
    return Response(status_code=status, headers={"Content-Type": "application/json"}, description=jsonify({"ok": True, "data": data}))


def _err(message: str, status: int = 400) -> Response:
    return Response(status_code=status, headers={"Content-Type": "application/json"}, description=jsonify({"ok": False, "error": message}))


def _route(fn):
    """Wrap a handler with IP/token guard + a uniform `{ok, error}` on failure."""
    @wraps(fn)
    def wrapper(request):
        guard = api_guard(request)
        if guard:
            return guard
        try:
            return fn(request)
        except Exception as exc:  # noqa: BLE001 — never leak a raw 500 out of the API
            logger.exception("api handler failed")
            return _err(str(exc), 500)
    return wrapper


def _json_body(request) -> dict:
    """Parse a JSON request body into a dict ({} if empty/invalid)."""
    json_fn = getattr(request, "json", None)
    if callable(json_fn):
        try:
            data = json_fn()
        except Exception:
            data = None
        if isinstance(data, dict):
            return data

    body = getattr(request, "body", None)
    if not body:
        return {}
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_source_spec(data: dict) -> SourceConfig | None:
    """Build a SourceConfig from a JSON source spec (`source` name or manual fields)."""
    source_name = (data.get("source", None) or "").strip()
    if source_name:
        for cfg in load_sources():
            if cfg.name == source_name:
                return cfg
        return None
    name = (data.get("name", None) or "").strip() or "manual"
    gatherer = (data.get("gatherer", None) or "").strip()
    url = (data.get("url", None) or "").strip()
    if not gatherer or not url:
        return None
    return SourceConfig(name=name, gatherer=gatherer, url=url)


def _parse_rules(data: dict) -> list[CategoryRule] | None:
    rules = data.get("rules")
    if rules is None:
        return None
    if isinstance(rules, dict):
        rules = [rules]
    return [CategoryRule(**r) for r in rules]


def _q(request, key: str) -> str | None:
    value = request.query_params.get(key, None)
    if value is None:
        return None
    try:
        return unquote_plus(value)
    except (TypeError, ValueError):
        return value


def _q_dt(request, key: str) -> datetime | None:
    value = _q(request, key)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _q_int(request, key: str, default: int | None) -> int | None:
    value = _q(request, key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
#endregion


#region: routes
def register(app) -> None:
    prefix = f"/api/{VERSION}"

    # -- read ----------------------------------------------------------------
    @app.get(f"{prefix}/stats")
    @_route
    def api_stats(request):
        with Session(engine) as session:
            ov = stats.overview(session)
            ov["last_ingest"] = stats.read_last_ingest()
        return _ok(ov)

    @app.get(f"{prefix}/sources")
    @_route
    def api_sources(request):
        with Session(engine) as session:
            return _ok(stats.sources(session))

    @app.get(f"{prefix}/events")
    @_route
    def api_events(request):
        start = _q_dt(request, "start")
        end = _q_dt(request, "end")
        category = _q(request, "category")
        limit = _q_int(request, "limit", DEFAULT_LIMIT)
        with Session(engine) as session:
            events = query_events(session, start=start, end=end, category=category, limit=limit)
            names = source_names(session, events)
        return _ok([to_fullcalendar(e, names.get(e.source_id)) for e in events])

    @app.get(f"{prefix}/events/:id")
    @_route
    def api_event(request):
        event_id = request.path_params.get("id", None)
        with Session(engine) as session:
            dump = stats.event_dump(session, event_id)
        if dump is None:
            return _err("not found", 404)
        return _ok(dump)

    @app.get(f"{prefix}/stale")
    @_route
    def api_stale(request):
        with Session(engine) as session:
            return _ok(stats.stale_events(session))

    @app.get(f"{prefix}/coherence")
    @_route
    def api_coherence(request):
        return _ok(coherence_check())

    @app.get(f"{prefix}/logs")
    @_route
    def api_logs(request):
        n = _q_int(request, "n", LOG_TAIL_LINES)
        return _ok({"lines": read_log_tail(n or LOG_TAIL_LINES)})

    @app.get(f"{prefix}/tests")
    @_route
    def api_tests_list(request):
        return _ok(collect_tests())

    # -- write ---------------------------------------------------------------
    @app.post(f"{prefix}/ingest")
    @_route
    def api_ingest(request):
        data = _json_body(request)
        dry_run = data.get("dry_run", True)
        return _ok({"dry_run": dry_run, "sources": run_report(dry_run=dry_run)})

    @app.post(f"{prefix}/retag")
    @_route
    def api_retag(request):
        data = _json_body(request)
        from_cat = (data.get("from", None) or "").strip()
        to_cat = (data.get("to", None) or "").strip() or None
        dry_run = data.get("dry_run", True)
        if not from_cat:
            return _err("'from' is required")
        with Session(engine) as session:
            changed, preview = retag(session, from_cat, to_cat)
            if not dry_run:
                session.commit()
        return _ok({"changed": changed, "dry_run": dry_run, "preview": [{"title": t, "before": b, "after": a} for t, b, a in preview]})

    @app.post(f"{prefix}/wipe/begin")
    @_route
    def api_wipe_begin(request):
        challenge = secrets.token_urlsafe(24)
        _pending_wipes[challenge] = time.time() + _WIPE_TTL
        return _ok({"challenge": challenge})

    @app.post(f"{prefix}/wipe/confirm")
    @_route
    def api_wipe_confirm(request):
        challenge = (_json_body(request).get("challenge", None) or "").strip()
        if not challenge:
            return _err("challenge is required")
        deadline = _pending_wipes.get(challenge)
        if deadline is None or time.time() > deadline:
            _pending_wipes.pop(challenge, None)
            return _err("invalid or expired challenge")
        result = wipe_all()
        _pending_wipes.pop(challenge, None)
        return _ok(result)

    @app.post(f"{prefix}/tests")
    @_route
    def api_tests_run(request):
        data = _json_body(request)
        test_id = (data.get("test", None) or "").strip() or None
        rc, output = run_tests(test_id)
        return _ok({"exit": rc, "output": output})

    # -- pipeline stages -----------------------------------------------------
    @app.post(f"{prefix}/pipeline/gather")
    @_route
    def api_pipeline_gather(request):
        cfg = _resolve_source_spec(_json_body(request))
        if cfg is None:
            return _err("bad source spec")
        result = load_gatherer(cfg.gatherer)(cfg)
        return _ok(result.model_dump(mode="json"))

    @app.post(f"{prefix}/pipeline/sieve")
    @_route
    def api_pipeline_sieve(request):
        cfg = _resolve_source_spec(_json_body(request))
        if cfg is None:
            return _err("bad source spec")
        run_fn = load_gatherer(cfg.gatherer)
        with Session(engine) as session:
            sieved, _ = process_source(session, cfg, run_fn, dry_run=True)
        return _ok(sieved.model_dump(mode="json"))

    @app.post(f"{prefix}/pipeline/decide")
    @_route
    def api_pipeline_decide(request):
        data = _json_body(request)
        cfg = _resolve_source_spec(data)
        if cfg is None:
            return _err("bad source spec")
        dry_run = data.get("dry_run", True)
        run_fn = load_gatherer(cfg.gatherer)
        with Session(engine) as session:
            sieved, report = process_source(session, cfg, run_fn, dry_run=dry_run)
            if not dry_run:
                session.commit()
        return _ok({"dry_run": dry_run, "report": report, "sieved": sieved.model_dump(mode="json")})

    @app.post(f"{prefix}/pipeline/categorize")
    @_route
    def api_pipeline_categorize(request):
        data = _json_body(request)
        cfg = _resolve_source_spec(data)
        if cfg is None:
            return _err("bad source spec")
        custom_rules = _parse_rules(data)
        include_configured = data.get("include_configured", True)
        dry_run = data.get("dry_run", True)

        if custom_rules is None:
            rules = None  # configured
        else:
            rules = (resolve_rules(cfg) + custom_rules) if include_configured else custom_rules

        run_fn = load_gatherer(cfg.gatherer)
        if dry_run:
            result = run_fn(cfg)
            categorize(result.source, result.events, rules=rules)
            events = [{"title": e.title, "categories": e.categories} for e in result.events]
            return _ok({"dry_run": True, "events": events})
        with Session(engine) as session:
            sieved, report = process_source(session, cfg, run_fn, dry_run=False, rules=rules)
            session.commit()
        return _ok({"dry_run": False, "report": report, "sieved": sieved.model_dump(mode="json")})
#endregion
