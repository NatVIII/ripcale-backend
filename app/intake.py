"""Intake settings store (sources, gatherers, category symlinks).

Separate from `config.py` (system settings) so intake data can be edited by the
program (admin menu, future automation) without touching the hand-edited system
config. Backed by a YAML file (default `intake.yaml`, via `settings.intake_file`)
so it survives DB wipes.

`load()` is mtime-cached: it re-reads the file only when its mtime changes, so
frequent callers stay cheap while another process's writes still get picked up.
"""
#region: imports
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.config import settings
from app.schema import CategoryRule, GathererConfig, SourceConfig
#endregion


#region: model
class IntakeSettings(BaseModel):
    """The mutable intake data (separate file from system `config.yaml`)."""

    sources: list[SourceConfig] = Field(default_factory=list)
    gatherers: dict[str, GathererConfig] = Field(default_factory=dict)
    category_symlinks: dict[str, str] = Field(default_factory=dict)
    # Class-first: `{class: [category, ...]}`. `intake` = auto-ingested, `external` = exposed.
    category_definitions: dict[str, list[str]] = Field(default_factory=dict)
    # Categorization rules applied to every event (global scope).
    rules: list[CategoryRule] = Field(default_factory=list)
#endregion


#region: cache
_cache: dict = {"key": None, "data": None}
#endregion


#region: load
def load() -> IntakeSettings:
    """Read intake.yaml (cached by path+mtime); missing file -> empty defaults."""
    path = Path(settings.intake_file)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        _cache["key"] = None
        _cache["data"] = IntakeSettings()
        return _cache["data"]

    key = (str(path), mtime)
    if _cache["key"] == key and _cache["data"] is not None:
        return _cache["data"]

    raw = yaml.safe_load(path.read_text()) or {}
    intake = IntakeSettings(**raw)
    _cache["key"] = key
    _cache["data"] = intake
    return intake
#endregion


#region: save
def save(intake: IntakeSettings) -> None:
    """Write intake.yaml atomically (temp + rename), then invalidate the cache."""
    path = Path(settings.intake_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(intake.model_dump(), sort_keys=False))
    os.replace(tmp, path)
    _cache["key"] = None
    _cache["data"] = None
#endregion
