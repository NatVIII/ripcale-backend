"""Database wipe (IP-gated + CSRF, challenge-response confirmation).

`register(app)` is called from `app/admin.py`.

Two-step confirmation:
  1. GET  /debug/wipe      — a red "delete database" button (begins the wipe).
  2. POST /debug/wipe      — the server returns a random challenge; echo it back
     to confirm before the wipe actually runs.

The wipe empties the Event + Source tables and resets status/last-ingest, but
leaves the schema intact so the server keeps serving and a later ingest
repopulates. Thin client over `app.services.actions.wipe_begin/wipe_confirm`.
"""
#region: imports
from robyn import Response

from app.security import debug_csrf_token, debug_guard, form_data, verify_csrf
from app.services import actions
from app.services.actions import ActionError
from app.web import escape, page
#endregion


#region: helpers
def _html(body: str) -> Response:
    return Response(status_code=200, headers={"Content-Type": "text/html"}, description=body)


def _forbidden() -> Response:
    return Response(status_code=403, headers={"Content-Type": "text/html"}, description=page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ forbidden", "<p>invalid CSRF token</p>"))


def _arm_page() -> str:
    token = debug_csrf_token()
    return (
        "<p><strong>danger zone.</strong> this permanently deletes every event "
        "and source from the database, and resets run status + last ingest. "
        "the server keeps running, but you must re-ingest to repopulate.</p>"
        f"<form method='post' action='/debug/wipe'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<input type='hidden' name='stage' value='begin'>"
        f"<button type='submit' style='background:#b00;color:#fff;padding:.5rem 1rem;'>delete database</button>"
        f"</form>"
    )


def _confirm_page(challenge: str) -> str:
    token = debug_csrf_token()
    return (
        f"<p>echo the challenge below to confirm the wipe:</p>"
        f"<p><strong>{escape(challenge)}</strong></p>"
        f"<form method='post' action='/debug/wipe'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<input type='hidden' name='stage' value='confirm'>"
        f"<p><input name='challenge' size='60' autocomplete='off'></p>"
        f"<button type='submit' style='background:#b00;color:#fff;padding:.5rem 1rem;'>confirm wipe</button>"
        f"</form>"
    )
#endregion


#region: routes
def register(app) -> None:
    @app.get("/debug/wipe")
    def wipe_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        return _html(page("ripcale · wipe database", _arm_page(), back="/debug"))

    @app.post("/debug/wipe")
    def wipe_run(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()

        stage = form_data(request).get("stage", None)

        if stage == "begin":
            challenge = actions.wipe_begin()
            return _html(page("ripcale · wipe database", _confirm_page(challenge), back="/debug"))

        if stage == "confirm":
            challenge = (form_data(request).get("challenge", None) or "").strip()
            try:
                result = actions.wipe_confirm(challenge)
            except ActionError as exc:
                body = f"<p><strong>{escape(exc)}</strong> nothing was deleted.</p>"
                return _html(page("ripcale · wipe database", body, back="/debug"))
            body = (
                f"<p>database wiped: {result['events']} events, {result['sources']} sources deleted.</p>"
                "<p>server still running — run an ingest to repopulate.</p>"
            )
            return _html(page("ripcale · wipe database", body, back="/debug"))

        return _html(page("ripcale · wipe database", _arm_page(), back="/debug"))
#endregion
