"""Gatherer contract compliance tests.

The gatherer contract lives in `docs/GATHERER_CONTRACT.md` (the source of truth).
These tests assert the documented shape fields match the pydantic models and that
every gatherer declares a conforming `CONTRACT_VERSION`.
"""
#region: imports
import importlib
import pkgutil

import app.gatherers as gatherers_pkg
from app.schema import (
    GathererConfig,
    GathererResult,
    ImageRef,
    ScrapedEvent,
    SourceConfig,
)

from contract_helpers import read_contract_version
#endregion


#region: shapes
def test_source_config_fields_match_doc():
    assert set(SourceConfig.model_fields) == {
        "name", "gatherer", "url", "is_public", "priority", "default_categories",
        "default_location", "rules",
    }


def test_gatherer_config_fields_match_doc():
    assert set(GathererConfig.model_fields) == {"priority"}


def test_image_ref_fields_match_doc():
    assert set(ImageRef.model_fields) == {"url", "alt", "source_url"}


def test_scraped_event_fields_match_doc():
    assert set(ScrapedEvent.model_fields) == {
        "uid", "title", "description", "location", "url", "images", "start_at",
        "end_at", "timezone", "all_day", "rrule", "recurrence_id", "exdates",
        "categories", "raw",
    }


def test_gatherer_result_fields_match_doc():
    assert set(GathererResult.model_fields) == {"source", "events"}
#endregion


#region: per-gatherer version
def _gatherer_names() -> list[str]:
    return [m.name for m in pkgutil.iter_modules(gatherers_pkg.__path__) if m.ispkg]


def test_each_gatherer_version_matches_doc():
    version = read_contract_version("GATHERER_CONTRACT.md")
    names = _gatherer_names()
    assert names, "no gatherers discovered"
    for name in names:
        mod = importlib.import_module(f"app.gatherers.{name}.gatherer")
        assert mod.CONTRACT_VERSION == version, (
            f"gatherer {name!r} declares v{mod.CONTRACT_VERSION}, contract is v{version}"
        )
#endregion
