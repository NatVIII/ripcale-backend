"""Versioned JSON admin API (token + IP gated).

`register(app)` is called from `app/admin.py`. Every route is `/api/v1/...`,
guarded by `api_guard`, and returns a `{ok, data|error}` envelope. The handlers
are thin wrappers over `app.services.actions` (the single source of truth).
"""
#region: imports
import logging
from datetime import datetime
from functools import wraps
from urllib.parse import unquote_plus

from robyn import Response, jsonify

from app.logging import LOG_TAIL_LINES
from app.security import api_guard, json_body
from app.services import actions
from app.services.actions import ActionError
#endregion


VERSION = "v1"
logger = logging.getLogger(__name__)


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
        except ActionError as exc:
            return _err(str(exc), exc.status)
        except Exception as exc:  # noqa: BLE001 — never leak a raw 500 out of the API
            logger.exception("api handler failed")
            return _err(str(exc), 500)
    return wrapper


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
        return _ok(actions.overview())

    @app.get(f"{prefix}/sources")
    @_route
    def api_sources(request):
        return _ok(actions.sources())

    @app.get(f"{prefix}/status")
    @_route
    def api_status(request):
        return _ok(actions.status())

    @app.get(f"{prefix}/events")
    @_route
    def api_events(request):
        start = _q_dt(request, "start")
        end = _q_dt(request, "end")
        category = _q(request, "category")
        limit = _q_int(request, "limit", None)
        return _ok(actions.events(start=start, end=end, category=category, limit=limit))

    @app.get(f"{prefix}/events/:id")
    @_route
    def api_event(request):
        event_id = request.path_params.get("id", None)
        dump = actions.event(event_id)
        if dump is None:
            return _err("not found", 404)
        return _ok(dump)

    @app.get(f"{prefix}/stale")
    @_route
    def api_stale(request):
        return _ok(actions.stale())

    @app.get(f"{prefix}/coherence")
    @_route
    def api_coherence(request):
        return _ok(actions.coherence())

    @app.get(f"{prefix}/logs")
    @_route
    def api_logs(request):
        n = _q_int(request, "n", LOG_TAIL_LINES)
        return _ok({"lines": actions.logs(n or LOG_TAIL_LINES)})

    @app.get(f"{prefix}/tests")
    @_route
    def api_tests_list(request):
        return _ok(actions.tests_list())

    # -- write ---------------------------------------------------------------
    @app.post(f"{prefix}/ingest")
    @_route
    def api_ingest(request):
        return _ok(actions.ingest(dry_run=json_body(request).get("dry_run", True)))

    @app.post(f"{prefix}/retag")
    @_route
    def api_retag(request):
        data = json_body(request)
        return _ok(actions.retag(data.get("from") or "", data.get("to"), data.get("dry_run", True)))

    @app.post(f"{prefix}/wipe/begin")
    @_route
    def api_wipe_begin(request):
        return _ok({"challenge": actions.wipe_begin()})

    @app.post(f"{prefix}/wipe/confirm")
    @_route
    def api_wipe_confirm(request):
        return _ok(actions.wipe_confirm(json_body(request).get("challenge") or ""))

    @app.post(f"{prefix}/tests")
    @_route
    def api_tests_run(request):
        test_id = (json_body(request).get("test") or "").strip() or None
        return _ok(actions.tests_run(test_id))

    # -- pipeline stages -----------------------------------------------------
    @app.post(f"{prefix}/pipeline/gather")
    @_route
    def api_pipeline_gather(request):
        cfg = actions.resolve_source_spec(json_body(request))
        if cfg is None:
            return _err("bad source spec")
        return _ok(actions.gather(cfg))

    @app.post(f"{prefix}/pipeline/sieve")
    @_route
    def api_pipeline_sieve(request):
        cfg = actions.resolve_source_spec(json_body(request))
        if cfg is None:
            return _err("bad source spec")
        return _ok(actions.sieve(cfg))

    @app.post(f"{prefix}/pipeline/decide")
    @_route
    def api_pipeline_decide(request):
        data = json_body(request)
        cfg = actions.resolve_source_spec(data)
        if cfg is None:
            return _err("bad source spec")
        return _ok(actions.decide(cfg, dry_run=data.get("dry_run", True)))

    @app.post(f"{prefix}/pipeline/categorize")
    @_route
    def api_pipeline_categorize(request):
        data = json_body(request)
        cfg = actions.resolve_source_spec(data)
        if cfg is None:
            return _err("bad source spec")
        rules = actions.parse_rules(data)
        return _ok(actions.categorize(cfg, rules, include_configured=data.get("include_configured", True), dry_run=data.get("dry_run", True)))
#endregion
