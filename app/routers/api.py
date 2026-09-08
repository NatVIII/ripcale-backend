"""Versioned JSON admin API (token + IP gated).

`register(app)` is called from `app/admin.py`. Every route is `/api/v1/...`,
guarded by `api_guard`, and returns a `{ok, data|error}` envelope. This is the
API-first surface for admin/debug interactivity — thin wrappers over services.
"""
#region: imports
import json

from robyn import Response, jsonify
from sqlmodel import Session

from app.categorize import apply as categorize, resolve_rules
from app.db import engine
from app.ingest import process_source, run_report
from app.logging import LOG_TAIL_LINES, read_log_tail
from app.registry import load_gatherer, load_sources
from app.schema import CategoryRule, SourceConfig
from app.security import api_guard
from app.services import stats
from app.services.coherence import check as coherence_check
from app.services.retag import retag
from app.services.testrunner import collect_tests, run_tests
from app.services.wipe import wipe_all
#endregion


VERSION = "v1"


#region: helpers
def _ok(data, status: int = 200) -> Response:
    return Response(status_code=status, headers={"Content-Type": "application/json"}, description=jsonify({"ok": True, "data": data}))


def _err(message: str, status: int = 400) -> Response:
    return Response(status_code=status, headers={"Content-Type": "application/json"}, description=jsonify({"ok": False, "error": message}))


def _json_body(request) -> dict:
    """Parse a JSON request body into a dict ({} if empty/invalid)."""
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
#endregion


#region: routes
def register(app) -> None:
    prefix = f"/api/{VERSION}"

    # -- read ----------------------------------------------------------------
    @app.get(f"{prefix}/stats")
    def api_stats(request):
        guard = api_guard(request)
        if guard:
            return guard
        with Session(engine) as session:
            ov = stats.overview(session)
            ov["last_ingest"] = stats.read_last_ingest()
        return _ok(ov)

    @app.get(f"{prefix}/sources")
    def api_sources(request):
        guard = api_guard(request)
        if guard:
            return guard
        with Session(engine) as session:
            return _ok(stats.sources(session))

    @app.get(f"{prefix}/events/:id")
    def api_event(request):
        guard = api_guard(request)
        if guard:
            return guard
        event_id = request.path_params.get("id", None)
        with Session(engine) as session:
            dump = stats.event_dump(session, event_id)
        if dump is None:
            return _err("not found", 404)
        return _ok(dump)

    @app.get(f"{prefix}/stale")
    def api_stale(request):
        guard = api_guard(request)
        if guard:
            return guard
        with Session(engine) as session:
            return _ok(stats.stale_events(session))

    @app.get(f"{prefix}/coherence")
    def api_coherence(request):
        guard = api_guard(request)
        if guard:
            return guard
        return _ok(coherence_check())

    @app.get(f"{prefix}/logs")
    def api_logs(request):
        guard = api_guard(request)
        if guard:
            return guard
        n = LOG_TAIL_LINES
        try:
            n = int((request.query_params.get("n", None) or LOG_TAIL_LINES))
        except (TypeError, ValueError):
            n = LOG_TAIL_LINES
        return _ok({"lines": read_log_tail(n)})

    @app.get(f"{prefix}/tests")
    def api_tests_list(request):
        guard = api_guard(request)
        if guard:
            return guard
        return _ok(collect_tests())

    # -- write ---------------------------------------------------------------
    @app.post(f"{prefix}/ingest")
    def api_ingest(request):
        guard = api_guard(request)
        if guard:
            return guard
        data = _json_body(request)
        dry_run = data.get("dry_run", True)
        return _ok(run_report(dry_run=dry_run))

    @app.post(f"{prefix}/retag")
    def api_retag(request):
        guard = api_guard(request)
        if guard:
            return guard
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

    @app.post(f"{prefix}/wipe")
    def api_wipe(request):
        guard = api_guard(request)
        if guard:
            return guard
        data = _json_body(request)
        if not data.get("confirm"):
            return _err("confirm: true is required to wipe")
        return _ok(wipe_all())

    @app.post(f"{prefix}/tests")
    def api_tests_run(request):
        guard = api_guard(request)
        if guard:
            return guard
        data = _json_body(request)
        test_id = (data.get("test", None) or "").strip() or None
        rc, output = run_tests(test_id)
        return _ok({"exit": rc, "output": output})

    # -- pipeline stages -----------------------------------------------------
    @app.post(f"{prefix}/pipeline/gather")
    def api_pipeline_gather(request):
        guard = api_guard(request)
        if guard:
            return guard
        cfg = _resolve_source_spec(_json_body(request))
        if cfg is None:
            return _err("bad source spec")
        try:
            result = load_gatherer(cfg.gatherer)(cfg)
        except Exception as exc:
            return _err(str(exc), 500)
        return _ok(result.model_dump(mode="json"))

    @app.post(f"{prefix}/pipeline/sieve")
    def api_pipeline_sieve(request):
        guard = api_guard(request)
        if guard:
            return guard
        cfg = _resolve_source_spec(_json_body(request))
        if cfg is None:
            return _err("bad source spec")
        try:
            run_fn = load_gatherer(cfg.gatherer)
            with Session(engine) as session:
                sieved, _ = process_source(session, cfg, run_fn, dry_run=True)
        except Exception as exc:
            return _err(str(exc), 500)
        return _ok(sieved.model_dump(mode="json"))

    @app.post(f"{prefix}/pipeline/decide")
    def api_pipeline_decide(request):
        guard = api_guard(request)
        if guard:
            return guard
        data = _json_body(request)
        cfg = _resolve_source_spec(data)
        if cfg is None:
            return _err("bad source spec")
        dry_run = data.get("dry_run", True)
        try:
            run_fn = load_gatherer(cfg.gatherer)
            with Session(engine) as session:
                sieved, report = process_source(session, cfg, run_fn, dry_run=dry_run)
                if not dry_run:
                    session.commit()
        except Exception as exc:
            return _err(str(exc), 500)
        return _ok({"dry_run": dry_run, "report": report, "sieved": sieved.model_dump(mode="json")})

    @app.post(f"{prefix}/pipeline/categorize")
    def api_pipeline_categorize(request):
        guard = api_guard(request)
        if guard:
            return guard
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

        try:
            run_fn = load_gatherer(cfg.gatherer)
            if dry_run:
                result = run_fn(cfg)
                categorize(result.source, result.events, rules=rules)
                events = [{"title": e.title, "categories": e.categories} for e in result.events]
                return _ok({"dry_run": True, "events": events})
            with Session(engine) as session:
                sieved, report = process_source(session, cfg, run_fn, dry_run=False, rules=rules)
                session.commit()
        except Exception as exc:
            return _err(str(exc), 500)
        return _ok({"dry_run": False, "report": report, "sieved": sieved.model_dump(mode="json")})
#endregion
