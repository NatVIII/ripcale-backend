"""Archive (GC) page (IP-gated + CSRF) — F22.

Thin client over `app.services.actions.archive` (and `archived`/`restore` for
F22.02). `/debug/archive` previews candidates (dry-run); `/debug/archived` lists
archived events with per-row restore.
"""
#region: imports
from robyn import Response

from app.security import debug_csrf_token, debug_guard, form_data, verify_csrf
from app.services import actions
from app.services.archive import DEFAULT_ARCHIVE_LIMIT
from app.web import escape, page, table
#endregion


#region: helpers
def _html(body: str) -> Response:
    return Response(status_code=200, headers={"Content-Type": "text/html"}, description=body)


def _forbidden() -> Response:
    return Response(
        status_code=403,
        headers={"Content-Type": "text/html"},
        description=page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ forbidden", "<p>invalid CSRF token</p>"),
    )


def _form() -> str:
    token = debug_csrf_token()
    return (
        "<p>archives (soft-deletes) events: <em>expired</em> events (past "
        "<code>expire_past_days</code>) immediately, and <em>removed-at-source</em> "
        "events once they've been stale for <code>archive_grace_hours</code>. "
        "Archived events are hidden from the public read path and frozen — they "
        "stay archived (no auto un-archive) until restored explicitly.</p>"
        f"<form method='post' action='/debug/archive'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<p><label><input type='checkbox' name='dry_run' value='1' checked> dry-run (show result, don't write)</label></p>"
        f"<button type='submit'>archive</button>"
        f"</form>"
    )


def _preview(result: dict) -> str:
    if not result["preview"]:
        return "<p>nothing to archive.</p>"
    return "<h2>candidates</h2>" + table(
        ["title", "id", "reason"],
        [[p["title"], p["id"], p["reason"]] for p in result["preview"]],
    )


def _archived_table(rows: list[dict], token: str) -> str:
    if not rows:
        return "<p>no archived events.</p>"
    trs = "".join(
        "<tr>"
        f"<td><a href='/debug/event/{escape(r['id'])}'>{escape(r['title'])}</a></td>"
        f"<td>{escape(r['source'] or '')}</td>"
        f"<td>{escape(r['archived_reason'] or '')}</td>"
        f"<td>{escape(r['archived_at'] or '')}</td>"
        f"<td><form method='post' action='/debug/archived/{escape(r['id'])}/restore' style='display:inline'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<button type='submit'>restore</button></form></td>"
        "</tr>"
        for r in rows
    )
    return "<table><tr><th>title</th><th>source</th><th>reason</th><th>archived</th><th></th></tr>" + trs + "</table>"


def _parse_limit(request) -> int | None:
    raw = (request.query_params or {}).get("limit")
    if not raw:
        return DEFAULT_ARCHIVE_LIMIT
    try:
        return int(raw)
    except (TypeError, ValueError):
        return DEFAULT_ARCHIVE_LIMIT
#endregion


#region: routes
def register(app) -> None:
    @app.get("/debug/archive")
    def archive_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        preview = actions.archive(dry_run=True)
        body = _form() + _preview(preview)
        return _html(page("ripcale · archive", body, back="/debug"))

    @app.post("/debug/archive")
    def archive_run(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()

        dry_run = form_data(request).get("dry_run") == "1"
        result = actions.archive(dry_run=dry_run)

        action = "dry run — nothing written" if dry_run else "committed"
        body = (
            f"<p>{action} · {result['expired']} expired + {result['removed']} removed archived</p>"
            + _preview(result)
        )
        return _html(page("ripcale · archive", body, back="/debug/archive"))

    @app.get("/debug/archived")
    def archived_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        rows = actions.archived(_parse_limit(request))
        body = (
            f"<p>{len(rows)} archived events (most recent first; add <code>?limit=N</code> to change, 0 = all):</p>"
            + _archived_table(rows, debug_csrf_token())
        )
        return _html(page("ripcale · archived", body, back="/debug"))

    @app.post("/debug/archived/:id/restore")
    def archived_restore(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()

        event_id = request.path_params.get("id", None)
        restored = actions.restore(event_id)
        body = f"<p>{'restored' if restored else 'not restored (missing or already live)'} — {escape(event_id)}</p>"
        return _html(page("ripcale · archived", body, back="/debug/archived"))
#endregion
