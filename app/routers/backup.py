"""Backups page (IP-gated + CSRF) — F23.

Thin client over `app.services.actions.backups_status` / `backup_run` /
`backup_prune`. Lists existing tar.gz snapshots, shows the worker status, and
offers run-now + prune buttons.
"""
#region: imports
from robyn import Response

from app.security import debug_csrf_token, debug_guard, verify_csrf
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


def _table(rows: list[dict]) -> str:
    if not rows:
        return "<p>no backups yet.</p>"
    return table(
        ["filename", "size", "created"],
        [[r["filename"], f"{r['size']:,}", r["created_at"]] for r in rows],
    )
#endregion


#region: routes
def register(app) -> None:
    @app.get("/debug/backups")
    def backups_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        data = actions.backups_status()
        worker = data["worker"]
        token = debug_csrf_token()

        if worker["reason"]:
            status = f"worker disabled — {escape(worker['reason'])}"
        else:
            status = (
                f"worker {'running' if worker['running'] else 'idle'} · "
                f"{worker['runs']} runs · next {escape(worker['next_run_at'] or '—')}"
            )

        body = (
            f"<p>{status}</p>"
            f"<form method='post' action='/debug/backups/run' style='display:inline'>"
            f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
            f"<button type='submit'>backup now</button></form>"
            f"<form method='post' action='/debug/backups/prune' style='display:inline'>"
            f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
            f"<button type='submit'>prune</button></form>"
            + _table(data["backups"])
        )
        return _html(page("ripcale · backups", body, back="/debug"))

    @app.post("/debug/backups/run")
    def backups_run(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        result = actions.backup_run()
        if result.get("created"):
            body = f"<p>backup created — <code>{escape(result['filename'])}</code> ({result['size']:,} bytes, {result.get('pruned', 0)} pruned)</p>"
        else:
            body = f"<p>backup skipped — {escape(result.get('reason', 'unknown'))}</p>"
        body += _table(actions.backups_status()["backups"])
        return _html(page("ripcale · backups", body, back="/debug/backups"))

    @app.post("/debug/backups/prune")
    def backups_prune(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        result = actions.backup_prune()
        body = f"<p>pruned {result['pruned']} backup(s).</p>" + _table(result["backups"])
        return _html(page("ripcale · backups", body, back="/debug/backups"))
#endregion
