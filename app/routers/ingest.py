"""Full-ingest trigger (IP-gated + CSRF).

`register(app)` is called from `app/admin.py`.

Runs the same pipeline as `python -m app.ingest` — every configured source
through gather → sieve → decide — but from the browser. The dry-run checkbox is
checked by default (classify only, nothing written).
"""
#region: imports
from robyn import Response

from app.registry import load_sources
from app.security import debug_csrf_token, debug_guard, form_data, verify_csrf
from app.services import actions
from app.web import escape, page, table
#endregion


#region: helpers
_STATUS_EMOJI = {"ok": "🟢", "warning": "🟡", "error": "🔴"}


def _html(body: str) -> Response:
    return Response(status_code=200, headers={"Content-Type": "text/html"}, description=body)


def _forbidden() -> Response:
    return Response(status_code=403, headers={"Content-Type": "text/html"}, description=page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ forbidden", "<p>invalid CSRF token</p>"))


def _form() -> str:
    token = debug_csrf_token()
    count = len(load_sources())
    return (
        f"<p>runs the full pipeline across all {count} configured sources "
        "(gather → sieve → decide) — the same code as `python -m app.ingest`.</p>"
        f"<form method='post' action='/debug/ingest'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<p><label><input type='checkbox' name='dry_run' value='1' checked> "
        f"dry-run (show result, don't write)</label></p>"
        f"<button type='submit'>run ingest</button>"
        f"</form>"
    )


def _result_table(summaries: list[dict]) -> str:
    if not summaries:
        return "<p>no sources configured.</p>"
    rows = [
        [
            _STATUS_EMOJI.get(s.get("status"), "⚪"),
            s["name"],
            s.get("new", "—"),
            s.get("updated", "—"),
            s.get("unchanged", "—"),
            s.get("inserted", "—") if s.get("inserted") is not None else "—",
            s.get("updated_rows", "—") if s.get("updated_rows") is not None else "—",
            s.get("removed", "—") if s.get("removed") is not None else "—",
            s.get("message") or "",
        ]
        for s in summaries
    ]
    return table(["", "source", "new", "updated", "unchanged", "inserted", "rows updated", "removed", "message"], rows)
#endregion


#region: routes
def register(app) -> None:
    @app.get("/debug/ingest")
    def ingest_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        return _html(page("ripcale · ingest", _form(), back="/debug"))

    @app.post("/debug/ingest")
    def ingest_run(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()

        dry_run = form_data(request).get("dry_run") == "1"
        result = actions.ingest(dry_run=dry_run)

        banner = "<p>dry run — nothing written.</p>" if dry_run else "<p>committed.</p>"
        body = banner + _result_table(result["sources"])
        return _html(page("ripcale · ingest", body, back="/debug/ingest"))
#endregion
