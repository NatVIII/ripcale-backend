"""Overseer observability page (IP-gated + CSRF) — F67.04.

Shows the overseer worker's status and pending `event_merge` proposals (approve/
reject live on `/debug/approvals`), plus a "run scan now" button.
"""
#region: imports
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


def _payload(payload, key: str) -> str:
    if isinstance(payload, dict):
        return payload.get(key, "") or ""
    return ""
#endregion


#region: routes
def register(app) -> None:
    @app.get("/debug/overseer")
    def overseer_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        st = actions.overseer_status()
        pending = [a for a in actions.approvals_list(status="pending") if a["kind"] == "event_merge"]

        reason = f" · {escape(st['reason'])}" if st.get("reason") else ""
        body = (
            f"<p>overseer worker: enabled={st['enabled']}, scanned={st['scanned']} ticks, "
            f"pairs={st['pairs']}, decisions={st['decisions']}, interval={st['interval_seconds']}s{reason}</p>"
            f"<form method='post' action='/debug/overseer'>"
            f"<input type='hidden' name='csrf_token' value='{escape(debug_csrf_token())}'>"
            f"<button type='submit'>run scan now</button></form>"
        )
        if not pending:
            body += "<p>no pending merge proposals.</p>"
        else:
            trs = "".join(
                "<tr>"
                f"<td>{escape(_payload(a['payload'], 'canonical_id'))}</td>"
                f"<td>{escape(_payload(a['payload'], 'loser_id'))}</td>"
                f"<td>{escape(a['reason'] or '')}</td>"
                "</tr>"
                for a in pending
            )
            body += (
                f"<p>{len(pending)} pending merge proposal(s) — approve/reject at "
                f"<a href='/debug/approvals'>/debug/approvals</a>:</p>"
                "<table><tr><th>winner</th><th>loser</th><th>reason</th></tr>" + trs + "</table>"
            )
        return _html(page("ripcale · overseer", body, back="/debug"))

    @app.post("/debug/overseer")
    def overseer_run(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        result = actions.overseer_run()
        body = (
            f"<p>scan done: {result.get('pairs', 0)} candidate pair(s), "
            f"{result.get('merges', 0)} merge proposal(s) proposed.</p>"
        )
        return _html(page("ripcale · overseer", body, back="/debug/overseer"))
#endregion
