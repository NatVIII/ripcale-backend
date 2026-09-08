"""Mass retag (IP-gated + CSRF).

`register(app)` is called from `app/admin.py`.

Renames or removes one `class:name` category across the whole DB, with a dry-run
checkbox (checked by default) so you can preview the affected events before
committing.
"""
#region: imports
from robyn import Response
from sqlmodel import Session

from app.db import engine
from app.security import debug_csrf_token, debug_guard, form_data, verify_csrf
from app.services.retag import retag
from app.web import escape, page, table
#endregion


#region: helpers
def _html(body: str) -> Response:
    return Response(status_code=200, headers={"Content-Type": "text/html"}, description=body)


def _forbidden() -> Response:
    return Response(status_code=403, headers={"Content-Type": "text/html"}, description=page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ forbidden", "<p>invalid CSRF token</p>"))


def _form() -> str:
    token = debug_csrf_token()
    return (
        "<p>renames a category across every event (or removes it if 'to' is empty). "
        "Only <code>categories</code> changes — content_hash is untouched, so this "
        "sticks until the source event next changes.</p>"
        f"<form method='post' action='/debug/retag'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<p><label>from <input name='from' size='40' placeholder='intake:foo'></label></p>"
        f"<p><label>to <input name='to' size='40' placeholder='external:bar (leave empty to remove)'></label></p>"
        f"<p><label><input type='checkbox' name='dry_run' value='1' checked> dry-run (show result, don't write)</label></p>"
        f"<button type='submit'>retag</button>"
        f"</form>"
    )
#endregion


#region: routes
def register(app) -> None:
    @app.get("/debug/retag")
    def retag_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        return _html(page("ripcale · retag", _form(), back="/debug"))

    @app.post("/debug/retag")
    def retag_run(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()

        form = form_data(request)
        from_cat = (form.get("from", None) or "").strip()
        to_cat = (form.get("to", None) or "").strip() or None
        dry_run = form.get("dry_run") == "1"

        if not from_cat:
            return _html(page("ripcale · retag", "<p>a 'from' category is required.</p>", back="/debug"))

        with Session(engine) as session:
            changed, preview = retag(session, from_cat, to_cat)
            if not dry_run:
                session.commit()

        action = "dry run — nothing written" if dry_run else "committed"
        body = f"<p>{action} · {changed} events changed</p>"
        if preview:
            body += "<h2>affected events</h2>" + table(
                ["title", "before", "after"],
                [[title, before, after] for title, before, after in preview],
            )
        return _html(page("ripcale · retag", body, back="/debug/retag"))
#endregion
