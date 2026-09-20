"""Debug dashboard (IP-gated, non-secret).

`register(app)` is called from `app/admin.py`. Every route is guarded by
`debug_guard` (loopback always; other hosts only within `debug_allowed_cidrs`).
All operations are thin clients over `app.services.actions`.
"""
#region: imports
from datetime import datetime
from urllib.parse import unquote_plus

from robyn import Response, jsonify

from app.logging import LOG_TAIL_LINES
from app.security import debug_guard, session_guard
from app.services import actions, clock
from app.services.events import DEFAULT_LIMIT
from app.services.status import source_status
from app.timeutil import display_time
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


def _category_mapping_section(mapping: dict) -> str:
    """Render the configured category mapping, collapsed behind a <details>."""
    exposed = ", ".join(mapping["exposed_classes"]) or "—"
    def_rows = [[cls, ", ".join(names)] for cls, names in sorted(mapping["definitions"].items())]
    link_rows = [[internal, f"→ {external}"] for internal, external in sorted(mapping["symlinks"].items())]

    body = (
        f"<p>exposed classes: {escape(exposed)}</p>"
        + "<h3>definitions (class → names)</h3>"
        + (table(["class", "names"], def_rows) if def_rows else "<p>none</p>")
        + "<h3>symlinks (internal → external)</h3>"
        + (table(["internal", "external"], link_rows) if link_rows else "<p>none</p>")
    )
    return "<details><summary>category mapping (config)</summary>" + body + "</details>"


def _scheduler_line(sched: dict) -> str:
    if not sched["enabled"]:
        return "<p>ingest scheduler: disabled</p>"

    def fmt(iso):
        if not iso:
            return "—"
        try:
            return display_time(datetime.fromisoformat(iso)) or "—"
        except ValueError:
            return iso

    running = " · running…" if sched["running"] else ""
    return (
        f"<p>ingest scheduler: every {sched['interval_minutes']}m"
        f" · last {fmt(sched['last_run_at'])}"
        f" · next {fmt(sched['next_run_at'])}{running}</p>"
    )


def _debug_clock_banner() -> str:
    if not clock.debug_active():
        return ""
    return (
        "<p style='background:#b00;color:#fff;padding:.5rem 1rem'>"
        f"debug clock: {escape(clock.now().isoformat())} (frozen)"
        "</p>"
    )
#endregion


#region: routes
def register(app) -> None:
    # -- HTML dashboard -----------------------------------------------------
    @app.get("/debug")
    def dashboard(request):
        guard = session_guard(request)
        if guard:
            return Response(status_code=302, headers={"Location": "/debug/login"}, description="")

        ov = actions.overview()
        srcs = actions.sources()
        st = actions.status()
        statuses = st["statuses"]
        rollup = st["rollup"]
        mapping = actions.category_mapping()
        sched = actions.scheduler()

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
            _debug_clock_banner()
            + _coherence_section()
            + f"<p>events: {ov['events']} (upcoming {ov['upcoming']}, past {ov['past']})"
            f" · archived: {ov['archived']} · sources: {ov['sources']}</p>"
            + _scheduler_line(sched)
            + "<h2>categories</h2>"
            + table(
                ["category", "class", "exposed", "count", "symlink"],
                [
                    [
                        c["name"],
                        c["class"],
                        "✓" if c["exposed"] else "internal",
                        c["count"],
                        f"→ {mapping['symlinks'][c['name']]}" if c["name"] in mapping["symlinks"] else "",
                    ]
                    for c in mapping["categories"]
                ],
            )
            + _category_mapping_section(mapping)
            + "<h2>gatherers</h2>"
            + "".join(gatherer_blocks)
            + "<details><summary>status (raw)</summary>" + json_pre(statuses) + "</details>"
            + "<h2>last ingest</h2>"
            + (json_pre(ov["last_ingest"]) if ov["last_ingest"] else "<p>no ingest run yet</p>")
            + "<p><a href='/debug/stale'>stale events</a></p>"
            + "<p><a href='/debug/events'>events</a></p>"
            + "<p><a href='/debug/retag'>retag categories</a></p>"
            + "<p><a href='/debug/archive'>archive (gc)</a> · <a href='/debug/archived'>archived events</a></p>"
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
            trs = "".join(
                "<tr>"
                f"<td>{escape(s['source'] or '')}</td>"
                f"<td><a href='/debug/event/{escape(s['id'])}'>{escape(s['title'])}</a></td>"
                f"<td>{escape(s['id'])}</td>"
                f"<td>{escape(s['kind'])}</td>"
                f"<td>{escape(s['last_seen_at'] or '')}</td>"
                "</tr>"
                for s in stale
            )
            body = (
                f"<p>{len(stale)} stale events:</p>"
                "<table><tr><th>source</th><th>title</th><th>id</th><th>kind</th><th>last seen</th></tr>"
                + trs + "</table>"
            )
        return _html(page("ripcale · stale events", body))

    # -- HTML: all events ----------------------------------------------------
    @app.get("/debug/events")
    def events_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        q = request.query_params or {}

        raw_limit = q.get("limit", None)
        try:
            limit = int(raw_limit) if raw_limit else DEFAULT_LIMIT
        except (TypeError, ValueError):
            limit = DEFAULT_LIMIT

        raw_cat = q.get("category", None)
        category = unquote_plus(raw_cat) if raw_cat else None

        rows = actions.event_list(limit=limit, category=category)
        if not rows:
            body = "<p>no events.</p>"
        else:
            trs = "".join(
                "<tr>"
                f"<td><a href='/debug/event/{escape(r['id'])}'>{escape(r['title'])}</a></td>"
                f"<td>{escape(r['source'] or '')}</td>"
                f"<td>{escape(r['start_at_display'] or '')}</td>"
                f"<td>{escape(r['end_at_display'] or '')}</td>"
                f"<td>{escape(r['categories'])}</td>"
                f"<td>{'pinned' if r['pinned'] else ''}</td>"
                "</tr>"
                for r in rows
            )
            body = (
                f"<p>{len(rows)} events (add <code>?limit=N</code>, <code>?category=class:name</code>):</p>"
                "<table><tr><th>title</th><th>source</th><th>start</th><th>end</th><th>categories</th><th>pinned</th></tr>"
                + trs + "</table>"
            )
        return _html(page("ripcale · events", body, back="/debug"))

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
