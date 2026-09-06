"""Minimal, dependency-free HTML rendering helpers.

Used by `app/routers/debug.py` and `app/routers/pipeline.py` to build the
static (no-JS) dashboard and pipeline playground pages.
"""
#region: imports
import html as _html
import json
#endregion


#region: escaping
def escape(value) -> str:
    """HTML-escape a value for safe insertion into markup."""
    return _html.escape(str(value))
#endregion


#region: page shell
def page(title: str, body: str, *, back: str | None = None) -> str:
    """Wrap `body` in a minimal HTML document with shared nav + styling."""
    nav = (
        '<p><a href="/debug">debug home</a> · '
        '<a href="/debug/pipeline">pipeline</a> · '
        '<a href="/debug/ingest">ingest</a> · '
        '<a href="/debug/logs">logs</a></p>'
    )
    back_link = f'<p><a href="{escape(back)}">\u2190 back</a></p>' if back else ""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{escape(title)}</title>"
        "<style>"
        "body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;}"
        "pre{background:#f6f6f6;padding:1rem;overflow:auto;}"
        "table{border-collapse:collapse;}td,th{border:1px solid #ddd;padding:.35rem .6rem;text-align:left;}"
        "input,select,button{font-size:1rem;padding:.3rem;margin:.15rem 0;}"
        "</style></head>"
        f"<body>{nav}{back_link}<h1>{escape(title)}</h1>{body}</body></html>"
    )
#endregion


#region: snippets
def pre(text) -> str:
    """Render text inside a <pre> block."""
    return f"<pre>{escape(text)}</pre>"


def json_pre(obj) -> str:
    """Render an object as pretty-printed JSON inside a <pre> block."""
    return pre(json.dumps(obj, indent=2, default=str))


def table(headers: list[str], rows: list[list]) -> str:
    """Render a simple <table> from a header list and row lists."""
    th = "".join(f"<th>{escape(h)}</th>" for h in headers)
    trs = "".join(
        "<tr>" + "".join(f"<td>{escape(c)}</td>" for c in row) + "</tr>"
        for row in rows
    )
    return f"<table><tr>{th}</tr>{trs}</table>"
#endregion
