"""Approval queue page (IP-gated + CSRF) — F66.

Thin client over `app.services.actions.approvals_list/approval_approve/
approval_reject`. Lists pending LLM proposals (with approve/reject) and recently
resolved ones.
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


def _payload_preview(payload) -> str:
    if isinstance(payload, dict) and not payload:
        return "{}"
    return escape(json.dumps(payload, indent=2, ensure_ascii=False))


def _rows_html(rows: list[dict], token: str) -> str:
    if not rows:
        return "<p>no proposals.</p>"
    trs = []
    for r in rows:
        actions_html = ""
        if r["status"] == "pending":
            actions_html = (
                f"<form method='post' action='/debug/approvals/{escape(r['id'])}/approve' style='display:inline'>"
                f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
                f"<button type='submit'>approve</button></form> "
                f"<form method='post' action='/debug/approvals/{escape(r['id'])}/reject' style='display:inline'>"
                f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
                f"<button type='submit'>reject</button></form>"
            )
        trs.append(
            "<tr>"
            f"<td>{escape(r['kind'])}</td>"
            f"<td>{escape(r['source_name'] or '')}</td>"
            f"<td><pre style='margin:0'>{_payload_preview(r['payload'])}</pre></td>"
            f"<td>{escape(r['reason'] or '')}</td>"
            f"<td>{escape(r['status'])}</td>"
            f"<td>{actions_html}</td>"
            "</tr>"
        )
    header = "<tr><th>kind</th><th>source</th><th>payload</th><th>reason</th><th>status</th><th></th></tr>"
    return "<table>" + header + "".join(trs) + "</table>"
#endregion


#region: routes
def register(app) -> None:
    @app.get("/debug/approvals")
    def approvals_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        pending = actions.approvals_list(status="pending")
        resolved = actions.approvals_list()
        body = (
            f"<p>{len(pending)} pending proposal(s) — the LLM proposes, you approve or reject.</p>"
            + _rows_html(pending, debug_csrf_token())
            + f"<h2>recently resolved</h2>"
            + _rows_html([r for r in resolved if r["status"] != "pending"], debug_csrf_token())
        )
        return _html(page("ripcale · approvals", body, back="/debug"))

    @app.post("/debug/approvals/:id/approve")
    def approvals_approve(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        approval_id = request.path_params.get("id", None)
        try:
            actions.approval_approve(approval_id)
            result = "approved"
        except Exception as exc:  # noqa: BLE001 — show the failure on the page
            result = f"failed: {escape(exc)}"
        return _html(page("ripcale · approvals", f"<p>{result}</p>", back="/debug/approvals"))

    @app.post("/debug/approvals/:id/reject")
    def approvals_reject(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        approval_id = request.path_params.get("id", None)
        try:
            actions.approval_reject(approval_id)
            result = "rejected"
        except Exception as exc:  # noqa: BLE001
            result = f"failed: {escape(exc)}"
        return _html(page("ripcale · approvals", f"<p>{result}</p>", back="/debug/approvals"))
#endregion
