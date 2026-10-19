"""Pinned-event change conflicts page (IP-gated + CSRF) — F68.

Lists pending (and resolved) `EventConflict` rows, each with three actions:
ignore / apply / syncretize.
"""
#region: imports
import json

from robyn import Response

from app.security import debug_csrf_token, debug_guard, verify_csrf
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


def _incoming_preview(incoming) -> str:
    text = json.dumps(incoming, indent=2, ensure_ascii=False) if isinstance(incoming, dict) else str(incoming)
    return f"<pre style='margin:0'>{escape(text)}</pre>"


def _rows_html(rows: list[dict], token: str) -> str:
    if not rows:
        return "<p>no conflicts.</p>"
    trs = []
    for r in rows:
        actions_html = ""
        if r["status"] == "pending":
            actions_html = "".join(
                f"<form method='post' action='/debug/conflicts/{escape(r['id'])}/resolve' style='display:inline'>"
                f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
                f"<input type='hidden' name='action' value='{a}'>"
                f"<button type='submit'>{a}</button></form> "
                for a in ("ignore", "apply", "syncretize")
            )
        trs.append(
            "<tr>"
            f"<td><a href='/debug/event/{escape(r['event_id'])}'>{escape(r['event_id'])}</a></td>"
            f"<td>{escape(', '.join(r['changed_fields']) or '—')}</td>"
            f"<td>{_incoming_preview(r['incoming'])}</td>"
            f"<td>{escape(r['status'])}</td>"
            f"<td>{actions_html}</td>"
            "</tr>"
        )
    header = "<tr><th>event</th><th>changed</th><th>incoming</th><th>status</th><th></th></tr>"
    return "<table>" + header + "".join(trs) + "</table>"
#endregion


#region: routes
def register(app) -> None:
    @app.get("/debug/conflicts")
    def conflicts_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        pending = actions.conflicts_list(status="pending")
        resolved = actions.conflicts_list()
        body = (
            f"<p>{len(pending)} pending conflict(s) — pinned events whose source changed. "
            f"Choose: <em>ignore</em> (keep pinned), <em>apply</em> (adopt source), "
            f"<em>syncretize</em> (LLM merge).</p>"
            + _rows_html(pending, debug_csrf_token())
            + "<h2>resolved</h2>"
            + _rows_html([r for r in resolved if r["status"] != "pending"], debug_csrf_token())
        )
        return _html(page("ripcale · conflicts", body, back="/debug"))

    @app.post("/debug/conflicts/:id/resolve")
    def conflicts_resolve(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        conflict_id = request.path_params.get("id", None)
        action = (form_data(request).get("action") or "").strip()
        try:
            actions.conflict_resolve(conflict_id, action)
            result = f"resolved ({action})"
        except Exception as exc:  # noqa: BLE001
            result = f"failed: {escape(exc)}"
        return _html(page("ripcale · conflicts", f"<p>{result}</p>", back="/debug/conflicts"))
#endregion
