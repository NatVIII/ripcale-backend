"""Single-event admin page (IP-gated + CSRF) — F22.03.

`GET /debug/event/:id` shows one event (live or archived) with pin/unpin and
restore (if archived) actions. Thin client over `app.services.actions`.
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


def _not_found() -> Response:
    return Response(status_code=404, headers={"Content-Type": "text/html"}, description=page("ripcale · event", "<p>not found</p>", back="/debug"))


def _event_body(dump: dict, token: str) -> str:
    rows = [
        ["id", dump["id"]],
        ["source", dump["source"] or ""],
        ["title", dump["title"]],
        ["start", dump["start_at"] or ""],
        ["end", dump["end_at"] or ""],
        ["categories", dump["categories"]],
        ["pinned", "yes" if dump["pinned"] else "no"],
        ["archived", dump["archived_at"] or "no"],
        ["archived reason", dump["archived_reason"] or ""],
        ["last seen", dump["last_seen_at"] or ""],
    ]
    body = table(["field", "value"], rows)

    pin_label = "unpin" if dump["pinned"] else "pin"
    pin_value = "0" if dump["pinned"] else "1"
    body += (
        f"<form method='post' action='/debug/event/{escape(dump['id'])}/pin' style='display:inline'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<input type='hidden' name='pinned' value='{pin_value}'>"
        f"<button type='submit'>{pin_label}</button></form>"
    )
    if dump["archived_at"]:
        body += (
            f"<form method='post' action='/debug/event/{escape(dump['id'])}/restore' style='display:inline'>"
            f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
            f"<button type='submit'>restore</button></form>"
        )
    return body
#endregion


#region: routes
def register(app) -> None:
    @app.get("/debug/event/:id")
    def event_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        dump = actions.event(request.path_params.get("id", None))
        if dump is None:
            return _not_found()
        return _html(page("ripcale · event", _event_body(dump, debug_csrf_token()), back="/debug"))

    @app.post("/debug/event/:id/pin")
    def event_pin(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        event_id = request.path_params.get("id", None)
        pinned = form_data(request).get("pinned") == "1"
        actions.pin(event_id, pinned)
        dump = actions.event(event_id)
        body = f"<p>{'pinned' if pinned else 'unpinned'} — {escape(event_id)}</p>"
        if dump is not None:
            body += _event_body(dump, debug_csrf_token())
        return _html(page("ripcale · event", body, back=f"/debug/event/{event_id}"))

    @app.post("/debug/event/:id/restore")
    def event_restore(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        event_id = request.path_params.get("id", None)
        restored = actions.restore(event_id)
        dump = actions.event(event_id)
        body = f"<p>{'restored' if restored else 'not restored'} — {escape(event_id)}</p>"
        if dump is not None:
            body += _event_body(dump, debug_csrf_token())
        return _html(page("ripcale · event", body, back=f"/debug/event/{event_id}"))
#endregion
