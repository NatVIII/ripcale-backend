"""Admin authentication (IP-gated): login/logout + a login page.

`register(app)` is called from `app/admin.py`. The JSON login issues an opaque
session (returned in the body and set as an HttpOnly cookie); the HTML
`/debug/login` page does the same for the browser and redirects to `/debug`.
"""
#region: imports
from robyn import Response, jsonify

from app.security import (
    SESSION_COOKIE,
    cookie_value,
    debug_csrf_token,
    debug_guard,
    form_data,
    json_body,
    session_guard,
    verify_csrf,
)
from app.services import auth
from app.services.actions import ActionError
from app.web import escape, page
#endregion


#region: helpers
def _html(body: str) -> Response:
    return Response(status_code=200, headers={"Content-Type": "text/html"}, description=body)


def _forbidden() -> Response:
    return Response(status_code=403, headers={"Content-Type": "text/html"}, description=page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ forbidden", "<p>invalid CSRF token</p>"))


def _cookie(token: str) -> str:
    # NOTE: add `Secure` once the admin sits behind TLS.
    return f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/"


def _clear_cookie() -> str:
    return f"{SESSION_COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"


def _json_error(message: str, status: int) -> Response:
    return Response(status_code=status, headers={"Content-Type": "application/json"}, description=jsonify({"ok": False, "error": message}))


def _login_form(error: str | None = None) -> str:
    token = debug_csrf_token()
    err = f"<p><strong>{escape(error)}</strong></p>" if error else ""
    return (
        err
        + f"<form method='post' action='/debug/login'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<p><label>username <input name='username' autocomplete='username'></label></p>"
        f"<p><label>password <input type='password' name='password' autocomplete='current-password'></label></p>"
        f"<button type='submit'>log in</button>"
        f"</form>"
    )
#endregion


#region: routes
def register(app) -> None:
    @app.post("/api/v1/auth/login")
    def api_login(request):
        guard = debug_guard(request)  # IP only (not api_token-gated — this is the login)
        if guard:
            return guard
        body = json_body(request)
        username = body.get("username") or ""
        password = body.get("password") or ""
        try:
            token = auth.login(username, password, getattr(request, "ip_addr", None))
        except ActionError as exc:
            return _json_error(str(exc), exc.status)
        return Response(
            status_code=200,
            headers={"Content-Type": "application/json", "Set-Cookie": _cookie(token)},
            description=jsonify({"ok": True, "data": {"token": token, "expires_in": auth.SESSION_TTL}}),
        )

    @app.post("/api/v1/auth/logout")
    def api_logout(request):
        guard = session_guard(request)
        if guard:
            return guard
        auth.destroy_session(cookie_value(request, SESSION_COOKIE))
        return Response(
            status_code=200,
            headers={"Content-Type": "application/json", "Set-Cookie": _clear_cookie()},
            description=jsonify({"ok": True}),
        )

    @app.get("/debug/login")
    def login_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        return _html(page("ripcale · login", _login_form()))

    @app.post("/debug/login")
    def login_submit(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        form = form_data(request)
        username = form.get("username") or ""
        password = form.get("password") or ""
        try:
            token = auth.login(username, password, getattr(request, "ip_addr", None))
        except ActionError as exc:
            return _html(page("ripcale · login", _login_form(str(exc))))
        return Response(status_code=302, headers={"Location": "/debug", "Set-Cookie": _cookie(token)}, description="")
#endregion
