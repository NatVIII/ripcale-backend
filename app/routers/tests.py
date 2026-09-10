"""Run the pytest suite from the browser (IP-gated + CSRF).

`register(app)` is called from `app/admin.py`.

`GET /debug/tests` lists the collected tests (via `pytest --collect-only`) with a
"run all" button and a run button per test. `POST /debug/tests` runs the full
suite or a single test in a subprocess and shows pass/fail + output.
"""
#region: imports
from robyn import Response

from app.security import debug_csrf_token, debug_guard, form_data, verify_csrf
from app.services import actions
from app.web import escape, page, pre
#endregion


#region: helpers
def _html(body: str) -> Response:
    return Response(status_code=200, headers={"Content-Type": "text/html"}, description=body)


def _forbidden() -> Response:
    return Response(status_code=403, headers={"Content-Type": "text/html"}, description=page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ forbidden", "<p>invalid CSRF token</p>"))


def _run_form(test_id: str, label: str) -> str:
    token = debug_csrf_token()
    return (
        f"<form method='post' action='/debug/tests'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<input type='hidden' name='test' value='{escape(test_id)}'>"
        f"<button type='submit'>run</button> {escape(label)}"
        f"</form>"
    )


def _list_page(tests: list[str]) -> str:
    body = "<p>run the pytest suite — the same code as `python -m pytest`.</p>"
    body += _run_form("", "all tests")
    if not tests:
        body += "<p>no tests collected.</p>"
        return body

    by_file: dict[str, list[tuple[str, str]]] = {}
    for t in tests:
        file, _, name = t.partition("::")
        by_file.setdefault(file, []).append((t, name))

    blocks = []
    for file in sorted(by_file):
        rows = "".join(f"<p>{_run_form(t, name)}</p>" for t, name in by_file[file])
        blocks.append(f"<details><summary>{escape(file)}</summary>{rows}</details>")
    return body + "".join(blocks)
#endregion


#region: routes
def register(app) -> None:
    @app.get("/debug/tests")
    def tests_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        return _html(page("ripcale · tests", _list_page(actions.tests_list()), back="/debug"))

    @app.post("/debug/tests")
    def tests_run(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()

        test_id = (form_data(request).get("test", None) or "").strip()
        result = actions.tests_run(test_id or None)

        if result["exit"] == 0:
            banner = "<p>🟢 passed</p>"
        else:
            banner = f"<p>🔴 failed (exit {result['exit']})</p>"
        body = banner + (pre(result["output"]) if result["output"] else "")
        return _html(page("ripcale · tests", body, back="/debug/tests"))
#endregion
