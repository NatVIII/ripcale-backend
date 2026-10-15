"""Source registry: read the configured sources and import gatherers.

`load_sources()` and `load_gatherer()` are called from `app/ingest.run()` and
`app/routers/pipeline.py`.
"""
#region: imports
import importlib
from typing import Callable

from app.intake import load as load_intake
from app.schema import GathererResult, SourceConfig
#endregion


#region: sources
def load_sources() -> list[SourceConfig]:
    """Return the configured sources (parsed from intake.yaml)."""
    return list(load_intake().sources)


def source_priority(cfg: SourceConfig) -> int:
    """Resolve a source's priority (config-side): source override > gatherer default > 0."""
    if cfg.priority is not None:
        return cfg.priority
    gatherer = load_intake().gatherers.get(cfg.gatherer)
    return gatherer.priority if gatherer else 0


def gatherer_permanent(name: str) -> bool:
    """True when a gatherer's posts are permanent (never "removed at source", F21)."""
    return _gatherer_flag(name, "PERMANENT")


def gatherer_decide_before_insert(name: str) -> bool:
    """True when a gatherer's posts are enqueued for LLM resolution (F65)."""
    return _gatherer_flag(name, "DECIDE_BEFORE_INSERT")


def _gatherer_flag(name: str, attr: str) -> bool:
    """Read a gatherer capability constant (declared in its module, not config)."""
    try:
        mod = importlib.import_module(f"app.gatherers.{name}.gatherer")
    except ImportError:
        return False
    return bool(getattr(mod, attr, False))
#endregion


#region: gatherers
def load_gatherer(name: str) -> Callable[[SourceConfig], GathererResult]:
    """Import `app.gatherers.<name>.gatherer` and return its `run` callable."""
    mod = importlib.import_module(f"app.gatherers.{name}.gatherer")
    return mod.run
#endregion
