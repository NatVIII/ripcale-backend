"""Interactive pipeline playground (IP-gated + CSRF).

`register(app)` is called from `app/main.py`.

Lets you drive each pipeline stage from the browser — against a configured
source or an arbitrary URL — and see the complete, untruncated result:

  * /debug/pipeline          home page (links to the three stages)
  * /debug/pipeline/gather   run a gatherer, show the full GathererResult
  * /debug/pipeline/sieve    run a gatherer + diff vs DB (no writes)
  * /debug/pipeline/decide   run + diff + persist (writes)

POST handlers require the CSRF token embedded in the forms.
"""
#region: imports
import importlib
import pkgutil

import app.gatherers as gatherers_pkg
from robyn import Response, jsonify
from sqlmodel import Session

from app.db import engine
from app.ingest import process_source
from app.registry import load_gatherer, load_sources
from app.schema import SourceConfig
from app.security import debug_csrf_token, debug_guard, form_data, verify_csrf
from app.web import escape, json_pre, page, table
#endregion


#region: helpers
def _html(body: str) -> Response:
    return Response(status_code=200, headers={"Content-Type": "text/html"}, description=body)


def _forbidden() -> Response:
    return Response(status_code=403, headers={"Content-Type": "text/html"}, description=page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ forbidden", "<p>invalid CSRF token</p>"))


def _available_gatherers() -> list[str]:
    """Discover gatherers under app/gatherers that expose a `run`."""
    names = []
    for mod in pkgutil.iter_modules(gatherers_pkg.__path__):
        if not mod.ispkg:
            continue
        try:
            candidate = importlib.import_module(f"app.gatherers.{mod.name}.gatherer")
            if hasattr(candidate, "run"):
                names.append(mod.name)
        except Exception:
            continue
    return sorted(names)


def _resolve_source(form: dict) -> SourceConfig | None:
    """Build a SourceConfig from a submitted form (configured or manual)."""
    source_name = (form.get("source", None) or "").strip()
    if source_name and source_name != "manual":
        for cfg in load_sources():
            if cfg.name == source_name:
                return cfg
        return None

    name = (form.get("name", None) or "").strip() or "manual"
    gatherer = (form.get("gatherer", None) or "").strip()
    url = (form.get("url", None) or "").strip()
    if not gatherer or not url:
        return None
    return SourceConfig(name=name, gatherer=gatherer, url=url)


def _form(action: str, note: str, *, extra: str = "") -> str:
    """Render the shared source-selection form for a stage (with optional extras)."""
    token = debug_csrf_token()
    source_opts = "".join(
        f"<option value='{escape(s.name)}'>{escape(s.name)}</option>" for s in load_sources()
    )
    gatherer_opts = "".join(f"<option value='{m}'>{m}</option>" for m in _available_gatherers())
    return (
        f"<form method='post' action='{action}'>"
        f"<input type='hidden' name='csrf_token' value='{escape(token)}'>"
        f"<p><label>source <select name='source'><option value='manual'>— manual —</option>{source_opts}</select></label></p>"
        f"<p><label>gatherer <select name='gatherer'>{gatherer_opts}</select></label></p>"
        f"<p><label>name <input name='name' placeholder='source name (manual)'></label></p>"
        f"<p><label>url <input name='url' size='70' placeholder='https://...'></label></p>"
        f"{extra}"
        f"<button type='submit'>run</button>"
        f"</form><p><em>{note}</em></p>"
    )
#endregion


#region: routes
def register(app) -> None:
    # -- home ---------------------------------------------------------------
    @app.get("/debug/pipeline")
    def pipeline_home(request):
        guard = debug_guard(request)
        if guard:
            return guard
        body = (
            "<p>Run one pipeline stage against a configured source or a manual URL.</p>"
            "<ul>"
            "<li><a href='/debug/pipeline/gather'>gather</a> — run a gatherer, show the full GathererResult</li>"
            "<li><a href='/debug/pipeline/sieve'>sieve</a> — run + diff vs the DB (no writes)</li>"
            "<li><a href='/debug/pipeline/decide'>decide</a> — run + diff + persist (writes)</li>"
            "</ul>"
        )
        return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline", body))

    # -- gather -------------------------------------------------------------
    @app.get("/debug/pipeline/gather")
    def gather_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · gather", _form("/debug/pipeline/gather", "Runs the gatherer and shows the complete, untruncated GathererResult."), back="/debug/pipeline"))

    @app.post("/debug/pipeline/gather")
    def gather_run(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        cfg = _resolve_source(form_data(request))
        if cfg is None:
            return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · gather", "<p>missing source (pick one) or gatherer+url</p>", back="/debug/pipeline"))
        result = load_gatherer(cfg.gatherer)(cfg)
        body = f"<p>source: {escape(cfg.name)} · events: {len(result.events)}</p>" + json_pre(result.model_dump(mode="json"))
        return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · gather", body, back="/debug/pipeline"))

    # -- sieve --------------------------------------------------------------
    @app.get("/debug/pipeline/sieve")
    def sieve_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · sieve", _form("/debug/pipeline/sieve", "Runs the gatherer and diffs against the DB. Read-only."), back="/debug/pipeline"))

    @app.post("/debug/pipeline/sieve")
    def sieve_run(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        cfg = _resolve_source(form_data(request))
        if cfg is None:
            return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · sieve", "<p>missing source or gatherer+url</p>", back="/debug/pipeline"))
        run_fn = load_gatherer(cfg.gatherer)
        with Session(engine) as session:
            sieved, _ = process_source(session, cfg, run_fn, dry_run=True)
        body = f"<p>{len(sieved.new)} new · {len(sieved.updated)} updated · {sieved.unchanged} unchanged</p>"
        body += "<h2>new</h2>" + table(
            ["id", "title", "categories"],
            [[e.id, e.event.title, ", ".join(e.event.categories)] for e in sieved.new],
        )
        body += "<h2>updated</h2>" + table(
            ["id", "title", "changed"],
            [[e.id, e.event.title, ", ".join(e.changed_fields)] for e in sieved.updated],
        )
        body += "<h2>full result</h2>" + json_pre(sieved.model_dump(mode="json"))
        return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · sieve", body, back="/debug/pipeline"))

    # -- decide -------------------------------------------------------------
    @app.get("/debug/pipeline/decide")
    def decide_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        dry_run = (
            "<p><label><input type='checkbox' name='dry_run' value='1' checked> "
            "dry-run (show result, don't write)</label></p>"
        )
        return _html(page(
            "ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · decide",
            _form("/debug/pipeline/decide", "Runs the full pipeline. Uncheck dry-run to commit.", extra=dry_run),
            back="/debug/pipeline",
        ))

    @app.post("/debug/pipeline/decide")
    def decide_run(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        form = form_data(request)
        cfg = _resolve_source(form)
        if cfg is None:
            return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · decide", "<p>missing source or gatherer+url</p>", back="/debug/pipeline"))
        dry_run = form.get("dry_run") == "1"
        run_fn = load_gatherer(cfg.gatherer)
        with Session(engine) as session:
            sieved, report = process_source(session, cfg, run_fn, dry_run=dry_run)
            if not dry_run:
                session.commit()

        if dry_run:
            body = f"<p>dry run — nothing written · {len(sieved.new)} new · {len(sieved.updated)} updated · {sieved.unchanged} unchanged</p>"
            body += "<h2>new</h2>" + table(
                ["id", "title", "categories"],
                [[e.id, e.event.title, ", ".join(e.event.categories)] for e in sieved.new],
            )
            body += "<h2>updated</h2>" + table(
                ["id", "title", "changed"],
                [[e.id, e.event.title, ", ".join(e.changed_fields)] for e in sieved.updated],
            )
            body += "<h2>full result</h2>" + json_pre(sieved.model_dump(mode="json"))
        else:
            body = f"<p>inserted {report['inserted']} · updated {report['updated']} · unchanged {report['unchanged']} — committed</p>"
            body += "<h2>new</h2>" + table(
                ["id", "title"],
                [[e.id, e.event.title] for e in sieved.new],
            )
            body += "<h2>updated</h2>" + table(
                ["id", "title", "changed"],
                [[e.id, e.event.title, ", ".join(e.changed_fields)] for e in sieved.updated],
            )
        return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · decide", body, back="/debug/pipeline"))
#endregion
