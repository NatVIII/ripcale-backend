"""Backups page (IP-gated + CSRF) — F23 + F23.02.

Thin client over `app.services.actions.backups_status` / `backup_run` /
`backup_prune` / `backup_restore`. Lists existing tar.gz snapshots, shows the
worker status, and offers run-now, prune, and per-snapshot restore (two-step).
"""
#region: imports
from urllib.parse import quote

from robyn import Response

from app.security import debug_csrf_token, debug_guard, form_data, verify_csrf
from app.services import actions
from app.web import escape, page
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
    trs = "".join(
        "<tr>"
        f"<td><code>{escape(r['filename'])}</code></td>"
        f"<td>{r['size']:,}</td>"
        f"<td>{escape(r['created_at'])}</td>"
        f"<td><a href='/debug/backups/restore?filename={quote(r['filename'])}'>restore</a></td>"
        "</tr>"
        for r in rows
    )
    return "<table><tr><th>filename</th><th>size</th><th>created</th><th></th></tr>" + trs + "</table>"


def _confirm_form(filename: str) -> str:
    token = debug_csrf_token()
    return (
        "<p>Restoring <code>"
        + escape(filename)
        + "</code> will <strong>overwrite the live database and intake.yaml</strong> "
        "with the snapshot. A safety-net backup is taken automatically first. Restart "
        "the app afterwards.</p>"
        "<form method='post' action='/debug/backups/restore'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<input type='hidden' name='filename' value='{escape(filename)}'>"
        "<button type='submit'>restore now</button>"
        "</form>"
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

    @app.get("/debug/backups/restore")
    def backups_restore_form(request):
        guard = debug_guard(request)
        if guard:
            return guard
        filename = (request.query_params or {}).get("filename") or ""
        if not filename:
            body = "<p>no backup selected.</p>"
        else:
            body = _confirm_form(filename)
        return _html(page("ripcale · restore", body, back="/debug/backups"))

    @app.post("/debug/backups/restore")
    def backups_restore(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        filename = (form_data(request).get("filename") or "").strip()
        result = actions.backup_restore(filename, confirm=True)
        body = (
            f"<p>restored <code>{escape(result['filename'])}</code>"
            f" · safety backup <code>{escape(result['safety_backup'] or '—')}</code>"
            f" · <strong>restart recommended</strong></p>"
            + _table(actions.backups_status()["backups"])
        )
        return _html(page("ripcale · restore", body, back="/debug/backups"))
#endregion
