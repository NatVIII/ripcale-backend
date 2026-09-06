"""Source registry: read the configured sources and import modules.

`load_sources()` and `load_module()` are called from `app/ingest.run()` and
`app/routers/pipeline.py`.
"""
#region: imports
import importlib
from typing import Callable

from app.config import settings
from app.schema import ModuleResult, SourceConfig
#endregion


#region: sources
def load_sources() -> list[SourceConfig]:
    """Return the configured sources (parsed from config.yaml into settings)."""
    return list(settings.sources)
#endregion


#region: modules
def load_module(name: str) -> Callable[[SourceConfig], ModuleResult]:
    """Import `app.sources.<name>.module` and return its `run` callable."""
    mod = importlib.import_module(f"app.sources.{name}.module")
    return mod.run
#endregion
