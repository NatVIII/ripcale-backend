"""Single-event admin page (IP-gated + CSRF) — F22.03.

`GET /debug/event/:id` shows one event (live or archived) with pin/unpin and
restore (if archived) actions. Thin client over `app.services.actions`.
"""
#region: imports
import json

from robyn import Response

from app.security import debug_csrf_token, debug_guard, form_data, verify_csrf
from app.services import actions
from app.services.actions import ActionError
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
        ["uid", dump["uid"] or ""],
        ["title", dump["title"]],
        ["description", dump["description"] or ""],
        ["location", dump["location"] or ""],
        ["url", dump["url"] or ""],
        ["start (utc)", dump["start_at"] or ""],
        ["end (utc)", dump["end_at"] or ""],
        ["start (display)", dump["start_at_display"] or ""],
        ["end (display)", dump["end_at_display"] or ""],
        ["timezone", dump["timezone"] or ""],
        ["all day", "yes" if dump["all_day"] else "no"],
        ["rrule", dump["rrule"] or ""],
        ["recurrence_id", dump["recurrence_id"] or ""],
        ["redirect_to_id", dump["redirect_to_id"] or ""],
        ["categories", dump["categories"]],
        ["priority", "" if dump["priority"] is None else str(dump["priority"])],
        ["content_hash", dump["content_hash"] or ""],
        ["last seen", dump["last_seen_at"] or ""],
        ["created", dump["created_at"] or ""],
        ["updated", dump["updated_at"] or ""],
        ["pinned", "yes" if dump["pinned"] else "no"],
        ["archived", dump["archived_at"] or "no"],
        ["archived reason", dump["archived_reason"] or ""],
    ]
    body = table(["field", "value"], rows)

    images = dump["images"] or []
    if images:
        figures = []
        for img in images:
            badge = "hosted" if img["hosted"] else "external"
            caption = badge
            if img.get("source_url"):
                caption += f" · <a href='{escape(img['source_url'])}'>source</a>"
            if img.get("alt"):
                caption += f" · {escape(img['alt'])}"
            figures.append(
                "<figure style='display:inline-block;margin:0 1rem 1rem 0;max-width:200px;vertical-align:top'>"
                f"<img src='{escape(img['url'])}' alt='{escape(img.get('alt') or '')}' "
                "style='max-width:200px;max-height:200px;border:1px solid #ddd'>"
                f"<figcaption style='font-size:.8rem;word-break:break-all'>{caption}</figcaption>"
                "</figure>"
            )
        body += "<h2>images</h2>" + "".join(figures)

    if dump["exdates"]:
        body += "<h2>exdates</h2>" + table(["datetime"], [[d] for d in dump["exdates"]])

    body += f"<p><a href='/debug/event/{escape(dump['id'])}/edit'>edit</a></p>"

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


def _edit_form(dump: dict, token: str) -> str:
    def _checked(flag) -> str:
        return " checked" if flag else ""

    return (
        f"<form method='post' action='/debug/event/{escape(dump['id'])}/edit'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<p><label>title <input name='title' size='60' value='{escape(dump['title'])}'></label></p>"
        f"<p><label>description <textarea name='description' rows='4' cols='60'>{escape(dump['description'] or '')}</textarea></label></p>"
        f"<p><label>location <input name='location' size='60' value='{escape(dump['location'] or '')}'></label></p>"
        f"<p><label>url <input name='url' size='60' value='{escape(dump['url'] or '')}'></label></p>"
        f"<p><label>timezone <input name='timezone' size='40' value='{escape(dump['timezone'] or '')}'></label></p>"
        f"<p><label>start <input name='start_at' size='40' value='{escape(dump['start_at'] or '')}'></label></p>"
        f"<p><label>end <input name='end_at' size='40' value='{escape(dump['end_at'] or '')}'></label></p>"
        f"<p><label>recurrence_id <input name='recurrence_id' size='40' value='{escape(dump['recurrence_id'] or '')}'></label></p>"
        f"<p><label><input type='checkbox' name='all_day' value='1'{_checked(dump['all_day'])}> all-day</label></p>"
        f"<p><label>rrule <input name='rrule' size='60' value='{escape(dump['rrule'] or '')}'></label></p>"
        f"<p><label>redirect_to_id <input name='redirect_to_id' size='60' value='{escape(dump['redirect_to_id'] or '')}'></label></p>"
        f"<p><label>priority <input name='priority' type='number' value='{escape(dump['priority'] if dump['priority'] is not None else '')}'></label></p>"
        f"<p><label>categories <input name='categories' size='60' value='{escape(dump['categories'])}'></label></p>"
        f"<p><label>images (JSON) <textarea name='images' rows='4' cols='60'>{escape(json.dumps(dump['images']))}</textarea></label></p>"
        f"<p><label>exdates (JSON) <textarea name='exdates' rows='3' cols='60'>{escape(json.dumps(dump['exdates']))}</textarea></label></p>"
        f"<p><label><input type='checkbox' name='pinned' value='1' checked> pin (freeze this edit)</label></p>"
        f"<button type='submit'>save</button>"
        f"</form>"
    )
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

    @app.get("/debug/event/:id/edit")
    def event_edit_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        dump = actions.event(request.path_params.get("id", None))
        if dump is None:
            return _not_found()
        return _html(page("ripcale · edit event", _edit_form(dump, debug_csrf_token()), back=f"/debug/event/{dump['id']}"))

    @app.post("/debug/event/:id/edit")
    def event_edit_run(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()

        event_id = request.path_params.get("id", None)
        form = form_data(request)
        data = {
            "title": form.get("title", ""),
            "description": form.get("description", "") or None,
            "location": form.get("location", "") or None,
            "url": form.get("url", "") or None,
            "timezone": form.get("timezone", "") or None,
            "start_at": form.get("start_at", "") or None,
            "end_at": form.get("end_at", "") or None,
            "recurrence_id": form.get("recurrence_id", "") or None,
            "all_day": form.get("all_day") == "1",
            "rrule": form.get("rrule", "") or None,
            "redirect_to_id": form.get("redirect_to_id", "") or None,
            "priority": form.get("priority", "") or None,
            "categories": form.get("categories", ""),
            "images": form.get("images") or "[]",
            "exdates": form.get("exdates") or "[]",
            "pinned": form.get("pinned") == "1",
        }

        try:
            dump = actions.edit_event(event_id, data)
        except ActionError as exc:
            return _html(page("ripcale · edit event", f"<p>{escape(exc)}</p>", back=f"/debug/event/{event_id}/edit"))

        body = f"<p>saved — {escape(event_id)}</p>" + _event_body(dump, debug_csrf_token())
        return _html(page("ripcale · event", body, back=f"/debug/event/{event_id}"))
#endregion
