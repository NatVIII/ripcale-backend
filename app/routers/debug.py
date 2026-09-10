"""Debug dashboard (IP-gated, non-secret).

`register(app)` is called from `app/admin.py`. Every route is guarded by
`debug_guard` (loopback always; other hosts only within `debug_allowed_cidrs`).
All operations are thin clients over `app.services.actions`.
"""
#region: imports
from robyn import Response, jsonify

from app.logging import LOG_TAIL_LINES
from app.security import debug_guard
from app.services import actions
from app.services.status import source_status
from app.web import escape, json_pre, page, pre, table
#endregion


#region: helpers
_STATUS_EMOJI = {"ok": "🟢", "warning": "🟡", "error": "🔴", "never": "⚪"}


def _html(body: str) -> Response:
    return Response(status_code=200, headers={"Content-Type": "text/html"}, description=body)


def _coherence_section() -> str:
    """Render the live coherence checks; never raises (the page must always render)."""
    try:
        issues = actions.coherence()
    except Exception as exc:  # noqa: BLE001 — a broken check must not break /debug
        issues = [{"severity": "warning", "scope": "debug", "message": f"coherence check failed: {exc}"}]

    if not issues:
        return "<h2>coherence</h2><p>🟢 all good</p>"

    emoji = {"error": "🔴", "warning": "🟡"}
    lines = "".join(
        f"<p>{emoji.get(i['severity'], '⚠️')} {escape(i['scope'])}: {escape(i['message'])}</p>"
        for i in issues
    )
    return "<h2>coherence</h2>" + lines
#endregion


#region: routes
def register(app) -> None:
    # -- HTML dashboard -----------------------------------------------------
    @app.get("/debug")
    def dashboard(request):
        guard = debug_guard(request)
        if guard:
            return guard

        ov = actions.overview()
        srcs = actions.sources()
        st = actions.status()
        statuses = st["statuses"]
        rollup = st["rollup"]
        symlinks = actions.symlinks()

        by_gatherer: dict[str, list[dict]] = {}
        for s in srcs:
            by_gatherer.setdefault(s["gatherer"], []).append(s)

        gatherer_blocks = []
        for gatherer in sorted(by_gatherer):
            emoji = _STATUS_EMOJI.get(rollup.get(gatherer, "never"), "⚪")
            rows = [
                [
                    f"{_STATUS_EMOJI.get(source_status(statuses, s['name']), '⚪')} {source_status(statuses, s['name'])}",
                    s["name"],
                    s["event_count"],
                    s["last_fetched_at"] or "—",
                ]
                for s in by_gatherer[gatherer]
            ]
            gatherer_blocks.append(
                f"<details><summary>{emoji} {escape(gatherer)}</summary>"
                + table(["status", "name", "events", "last fetch"], rows)
                + "</details>"
            )

        body = (
            _coherence_section()
            + f"<p>events: {ov['events']} (upcoming {ov['upcoming']}, past {ov['past']})"
            f" · sources: {ov['sources']}</p>"
            + "<h2>categories</h2>"
            + table(
                ["category", "count", "symlink"],
                [
                    [c["name"], c["count"], f"→ {symlinks[c['name']]}" if c["name"] in symlinks else ""]
                    for c in ov["categories"]
                ],
            )
            + "<h2>gatherers</h2>"
            + "".join(gatherer_blocks)
            + "<details><summary>status (raw)</summary>" + json_pre(statuses) + "</details>"
            + "<h2>last ingest</h2>"
            + (json_pre(ov["last_ingest"]) if ov["last_ingest"] else "<p>no ingest run yet</p>")
            + "<p><a href='/debug/stale'>stale events</a></p>"
            + "<p><a href='/debug/retag'>retag categories</a></p>"
            + "<h2>danger zone</h2>"
            + "<p><a href='/debug/wipe'>wipe database</a></p>"
        )
        return _html(page("ripcale debug menu! (˶>⩊<˶)", body))

    # -- HTML: log tail ------------------------------------------------------
    @app.get("/debug/logs")
    def logs(request):
        guard = debug_guard(request)
        if guard:
            return guard
        tail = actions.logs()
        body = (
            f"<p>last {LOG_TAIL_LINES} log lines — reload to refresh.</p>"
            + (pre(tail) if tail else "<p>no log entries yet.</p>")
        )
        return _html(page("ripcale logs", body))

    # -- HTML: stale events ---------------------------------------------------
    @app.get("/debug/stale")
    def stale_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        stale = actions.stale()
        if not stale:
            body = "<p>no stale events.</p>"
        else:
            body = f"<p>{len(stale)} stale events (removed at source):</p>" + table(
                ["source", "title", "id", "last seen"],
                [[s["source"], s["title"], s["id"], s["last_seen_at"] or "—"] for s in stale],
            )
        return _html(page("ripcale · stale events", body))

    # -- JSON: stats --------------------------------------------------------
    @app.get("/debug/stats")
    def stats_json(request):
        guard = debug_guard(request)
        if guard:
            return guard
        return actions.overview()

    # -- JSON: sources ------------------------------------------------------
    @app.get("/debug/sources")
    def sources_json(request):
        guard = debug_guard(request)
        if guard:
            return guard
        return actions.sources()

    # -- JSON: single event dump -------------------------------------------
    @app.get("/debug/events/:id")
    def event_json(request):
        guard = debug_guard(request)
        if guard:
            return guard
        event_id = request.path_params.get("id", None)
        dump = actions.event(event_id)
        if dump is None:
            return Response(
                status_code=404,
                headers={"Content-Type": "application/json"},
                description=jsonify({"error": "not found"}),
            )
        return dump
#endregion
