"""Archive (GC) page (IP-gated + CSRF) — F22.

Thin client over `app.services.actions.archive`. GET previews the candidates
(dry-run); POST runs archiving with a dry-run checkbox (checked by default).
"""
#region: imports
from robyn import Response

from app.security import debug_csrf_token, debug_guard, form_data, verify_csrf
from app.services import actions
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
        "Archived events are hidden from the public read path but kept in the DB; "
        "they un-archive automatically if they reappear in their source.</p>"
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
#endregion
