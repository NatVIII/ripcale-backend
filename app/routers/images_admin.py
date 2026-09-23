"""Image GC page (IP-gated + CSRF) — F18.01.

Thin client over `app.services.actions.prune_images`. `/debug/images` previews
orphaned hosted image files (dry-run); a checkbox commits the deletion.
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


def _form() -> str:
    token = debug_csrf_token()
    return (
        "<p>deletes hosted image files under <code>data/images/</code> that no "
        "<em>live</em> event references. Images used only by archived events are "
        "also removed (they re-host on restore).</p>"
        f"<form method='post' action='/debug/images'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<p><label><input type='checkbox' name='dry_run' value='1' checked> dry-run (show result, don't delete)</label></p>"
        f"<button type='submit'>prune</button>"
        f"</form>"
    )


def _preview(result: dict) -> str:
    if not result["preview"]:
        return "<p>no orphaned images.</p>"
    return "<h2>orphans</h2>" + table(["filename"], [[fn] for fn in result["preview"]])
#endregion


#region: routes
def register(app) -> None:
    @app.get("/debug/images")
    def images_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        preview = actions.prune_images(dry_run=True)
        return _html(page("ripcale · images", _form() + _preview(preview), back="/debug"))

    @app.post("/debug/images")
    def images_run(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()

        dry_run = form_data(request).get("dry_run") == "1"
        result = actions.prune_images(dry_run=dry_run)

        action = "dry run — nothing deleted" if dry_run else "committed"
        body = (
            f"<p>{action} · {result['orphan_count']} orphans ({result['bytes_freed']} bytes) "
            f"of {result['on_disk']} on disk, {result['referenced']} referenced</p>"
            + _preview(result)
        )
        return _html(page("ripcale · images", body, back="/debug/images"))
#endregion
