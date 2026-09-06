"""Debug dashboard (IP-gated, non-secret).

`register(app)` is called from `app/main.py`. Handlers are dispatched by the
Robyn router. Every route is guarded by `debug_guard` (loopback always; other
hosts only within `debug_allowed_cidrs`).

Provides a static HTML overview at `/debug` plus JSON endpoints for programmatic
inspection.
"""
#region: imports
from robyn import Response, jsonify
from sqlmodel import Session

from app.db import engine
from app.security import debug_guard
from app.services import stats
from app.web import json_pre, page, table
#endregion


#region: helpers
def _html(body: str) -> Response:
    return Response(status_code=200, headers={"Content-Type": "text/html"}, description=body)
#endregion


#region: routes
def register(app) -> None:
    # -- HTML dashboard -----------------------------------------------------
    @app.get("/debug")
    def dashboard(request):
        guard = debug_guard(request)
        if guard:
            return guard

        with Session(engine) as session:
            ov = stats.overview(session)
            srcs = stats.sources(session)
            last = stats.read_last_ingest()

        body = (
            f"<p>events: {ov['events']} (upcoming {ov['upcoming']}, past {ov['past']})"
            f" · sources: {ov['sources']}</p>"
            + "<h2>categories</h2>"
            + table(
                ["category", "count"],
                [[c["name"], c["count"]] for c in ov["categories"]],
            )
            + "<h2>sources</h2>"
            + table(
                ["name", "module", "events", "last fetch"],
                [
                    [s["name"], s["module"], s["event_count"], s["last_fetched_at"] or "—"]
                    for s in srcs
                ],
            )
            + "<h2>last ingest</h2>"
            + (json_pre(last) if last else "<p>no ingest run yet</p>")
        )
        return _html(page("ripcale debug menu! (˶>⩊<˶)", body))

    # -- JSON: stats --------------------------------------------------------
    @app.get("/debug/stats")
    def stats_json(request):
        guard = debug_guard(request)
        if guard:
            return guard
        with Session(engine) as session:
            ov = stats.overview(session)
            ov["last_ingest"] = stats.read_last_ingest()
        return ov

    # -- JSON: sources ------------------------------------------------------
    @app.get("/debug/sources")
    def sources_json(request):
        guard = debug_guard(request)
        if guard:
            return guard
        with Session(engine) as session:
            return stats.sources(session)

    # -- JSON: single event dump -------------------------------------------
    @app.get("/debug/events/:id")
    def event_json(request):
        guard = debug_guard(request)
        if guard:
            return guard
        event_id = request.path_params.get("id", None)
        with Session(engine) as session:
            dump = stats.event_dump(session, event_id)
        if dump is None:
            return Response(
                status_code=404,
                headers={"Content-Type": "application/json"},
                description=jsonify({"error": "not found"}),
            )
        return dump
#endregion
