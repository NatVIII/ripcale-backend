"""Interactive pipeline playground (IP-gated + CSRF).

`register(app)` is called from `app/admin.py`.

Lets you drive each pipeline stage from the browser — against a configured
source or an arbitrary URL — and see the complete, untruncated result:

  * /debug/pipeline          home page (links to the four stages)
  * /debug/pipeline/gather   run a gatherer, show the full GathererResult
  * /debug/pipeline/categorize  apply custom rules, show the resulting categories
  * /debug/pipeline/sieve    run a gatherer + diff vs DB (no writes)
  * /debug/pipeline/decide   run + diff + persist (writes)

POST handlers require the CSRF token embedded in the forms. All operations are
thin clients over `app.services.actions`.
"""
#region: imports
import importlib
import logging
import pkgutil

import app.gatherers as gatherers_pkg
from robyn import Response, jsonify
from app.registry import load_sources
from app.schema import CategoryRule
from app.security import debug_csrf_token, debug_guard, form_data, verify_csrf
from app.services import actions
from app.web import escape, json_pre, page, table

logger = logging.getLogger(__name__)
#endregion


#region: helpers
def _html(body: str) -> Response:
    return Response(status_code=200, headers={"Content-Type": "text/html"}, description=body)


def _forbidden() -> Response:
    return Response(status_code=403, headers={"Content-Type": "text/html"}, description=page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ forbidden", "<p>invalid CSRF token</p>"))


def _error_page(stage: str, exc: Exception) -> Response:
    """Log the failure and render a clear error page (instead of a bare 500)."""
    logger.exception("%s stage failed", stage)
    return _html(page(f"ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · {stage}", f"<p><strong>error:</strong> {escape(exc)}</p>", back="/debug/pipeline"))


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
        except Exception as exc:
            logger.warning("gatherer %r failed to import: %s", mod.name, exc)
            continue
    return sorted(names)


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
            "<li><a href='/debug/pipeline/categorize'>categorize</a> — apply custom rules, show the resulting categories (dry-run by default)</li>"
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
        cfg = actions.resolve_source_spec(form_data(request))
        if cfg is None:
            return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · gather", "<p>missing source (pick one) or gatherer+url</p>", back="/debug/pipeline"))
        try:
            data = actions.gather(cfg)
        except Exception as exc:
            return _error_page("gather", exc)
        body = f"<p>source: {escape(cfg.name)} · events: {len(data['events'])}</p>" + json_pre(data)
        return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · gather", body, back="/debug/pipeline"))

    # -- categorize ---------------------------------------------------------
    @app.get("/debug/pipeline/categorize")
    def categorize_page(request):
        guard = debug_guard(request)
        if guard:
            return guard
        extra = (
            "<p><label>mode <select name='mode'><option value='regex'>regex</option><option value='assign'>assign</option></select></label></p>"
            "<p><label>fields <input name='fields' placeholder='title,description or *'></label></p>"
            "<p><label>regex <input name='regex' size='60' placeholder='(?i)workshop'></label></p>"
            "<p><label>categories <input name='categories' placeholder='workshop,art (comma-separated)'></label></p>"
            "<p><label><input type='checkbox' name='include_configured' value='1' checked> include configured rules</label></p>"
            "<p><label><input type='checkbox' name='dry_run' value='1' checked> dry-run (show result, don't write)</label></p>"
        )
        return _html(page(
            "ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · categorize",
            _form("/debug/pipeline/categorize", "Applies custom categorization rules to a source's events (one rule per run).", extra=extra),
            back="/debug/pipeline",
        ))

    @app.post("/debug/pipeline/categorize")
    def categorize_run(request):
        guard = debug_guard(request)
        if guard:
            return guard
        if not verify_csrf(request):
            return _forbidden()
        form = form_data(request)
        cfg = actions.resolve_source_spec(form)
        if cfg is None:
            return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · categorize", "<p>missing source or gatherer+url</p>", back="/debug/pipeline"))

        mode = (form.get("mode", None) or "regex").strip() or "regex"
        fields = [f.strip() for f in (form.get("fields", None) or "").split(",") if f.strip()]
        regex = (form.get("regex", None) or "").strip() or None
        categories = [c.strip() for c in (form.get("categories", None) or "").split(",") if c.strip()]

        if not categories:
            return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · categorize", "<p>no categories given for the custom rule</p>", back="/debug/pipeline"))
        if mode == "regex" and not regex:
            return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · categorize", "<p>regex mode needs a pattern</p>", back="/debug/pipeline"))

        rule = CategoryRule(mode=mode, fields=fields, regex=regex, categories=categories)
        include_configured = form.get("include_configured") == "1"
        dry_run = form.get("dry_run") == "1"

        try:
            result = actions.categorize(cfg, [rule], include_configured=include_configured, dry_run=dry_run)
        except Exception as exc:
            return _error_page("categorize", exc)

        if dry_run:
            body = f"<p>source: {escape(cfg.name)} · events: {len(result['events'])} · dry run</p>"
            body += "<h2>resulting categories</h2>" + table(
                ["title", "categories"],
                [[e["title"], ", ".join(e["categories"])] for e in result["events"]],
            )
        else:
            body = f"<p>committed · inserted {result['report']['inserted']} · updated {result['report']['updated']} · unchanged {result['report']['unchanged']}</p>"
        return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · categorize", body, back="/debug/pipeline"))

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
        cfg = actions.resolve_source_spec(form_data(request))
        if cfg is None:
            return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · sieve", "<p>missing source or gatherer+url</p>", back="/debug/pipeline"))
        try:
            sieved = actions.sieve(cfg)
        except Exception as exc:
            return _error_page("sieve", exc)

        body = f"<p>{len(sieved['new'])} new · {len(sieved['updated'])} updated · {sieved['unchanged']} unchanged</p>"
        body += "<h2>new</h2>" + table(
            ["id", "title", "categories"],
            [[e["id"], e["event"]["title"], ", ".join(e["event"]["categories"])] for e in sieved["new"]],
        )
        body += "<h2>updated</h2>" + table(
            ["id", "title", "changed"],
            [[e["id"], e["event"]["title"], ", ".join(e["changed_fields"])] for e in sieved["updated"]],
        )
        body += "<h2>full result</h2>" + json_pre(sieved)
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
        cfg = actions.resolve_source_spec(form)
        if cfg is None:
            return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · decide", "<p>missing source or gatherer+url</p>", back="/debug/pipeline"))
        dry_run = form.get("dry_run") == "1"
        try:
            result = actions.decide(cfg, dry_run=dry_run)
        except Exception as exc:
            return _error_page("decide", exc)

        sieved = result["sieved"]
        if dry_run:
            body = f"<p>dry run — nothing written · {len(sieved['new'])} new · {len(sieved['updated'])} updated · {sieved['unchanged']} unchanged</p>"
            body += "<h2>new</h2>" + table(
                ["id", "title", "categories"],
                [[e["id"], e["event"]["title"], ", ".join(e["event"]["categories"])] for e in sieved["new"]],
            )
            body += "<h2>updated</h2>" + table(
                ["id", "title", "changed"],
                [[e["id"], e["event"]["title"], ", ".join(e["changed_fields"])] for e in sieved["updated"]],
            )
            body += "<h2>full result</h2>" + json_pre(sieved)
        else:
            report = result["report"]
            body = f"<p>inserted {report['inserted']} · updated {report['updated']} · unchanged {report['unchanged']} — committed</p>"
            body += "<h2>new</h2>" + table(
                ["id", "title"],
                [[e["id"], e["event"]["title"]] for e in sieved["new"]],
            )
            body += "<h2>updated</h2>" + table(
                ["id", "title", "changed"],
                [[e["id"], e["event"]["title"], ", ".join(e["changed_fields"])] for e in sieved["updated"]],
            )
        return _html(page("ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧ pipeline · decide", body, back="/debug/pipeline"))
#endregion
