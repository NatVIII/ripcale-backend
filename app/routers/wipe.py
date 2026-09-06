"""Database wipe (IP-gated + CSRF, two layers of verification).

`register(app)` is called from `app/admin.py`.

Two-layer confirmation:
  1. GET  /debug/wipe      — a red "delete database" button.
  2. POST /debug/wipe      — requires typing a sentence in full, then a
     second confirm button before the wipe actually runs.

The wipe empties the Event + Source tables and resets status/last-ingest, but
leaves the schema intact so the server keeps serving and a later ingest
repopulates.
"""
#region: imports
from robyn import Response

from app.security import debug_csrf_token, debug_guard, form_data, verify_csrf
from app.services.wipe import wipe_all
from app.web import escape, page
#endregion


#region: helpers
CONFIRM_SENTENCE = "I understand the data will be permanently deleted"


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
        f"<input type='hidden' name='stage' value='arm'>"
        f"<button type='submit' style='background:#b00;color:#fff;padding:.5rem 1rem;'>delete database</button>"
        f"</form>"
    )


def _confirm_page() -> str:
    token = debug_csrf_token()
    return (
        f"<p>type the sentence below <em>in full</em> to confirm:</p>"
        f"<p><strong>{escape(CONFIRM_SENTENCE)}</strong></p>"
        f"<form method='post' action='/debug/wipe'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<input type='hidden' name='stage' value='confirm'>"
        f"<p><input name='phrase' size='60' autocomplete='off'></p>"
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

        if stage == "arm":
            return _html(page("ripcale · wipe database", _confirm_page(), back="/debug"))

        if stage == "confirm":
            phrase = (form_data(request).get("phrase", None) or "").strip()
            if phrase != CONFIRM_SENTENCE:
                body = (
                    "<p><strong>sentence did not match.</strong> nothing was deleted.</p>"
                    + _confirm_page()
                )
                return _html(page("ripcale · wipe database", body, back="/debug"))

            result = wipe_all()
            body = (
                f"<p>database wiped: {result['events']} events, {result['sources']} sources deleted.</p>"
                "<p>server still running — run an ingest to repopulate.</p>"
            )
            return _html(page("ripcale · wipe database", body, back="/debug"))

        return _html(page("ripcale · wipe database", _arm_page(), back="/debug"))
#endregion
