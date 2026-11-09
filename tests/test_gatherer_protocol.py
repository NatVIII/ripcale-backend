"""Tests for the Gatherer protocol (F70.03)."""
#region: imports
import importlib

from app.gatherers.base import ChangeProbeGatherer, Gatherer
#endregion


def _gatherer(name: str):
    return importlib.import_module(f"app.gatherers.{name}.gatherer")


def test_all_gatherers_satisfy_the_core_contract():
    for name in ("elfsight", "ics", "hikerapi"):
        assert isinstance(_gatherer(name), Gatherer)


def test_only_hikerapi_satisfies_change_probe():
    assert isinstance(_gatherer("hikerapi"), ChangeProbeGatherer)
    assert not isinstance(_gatherer("elfsight"), ChangeProbeGatherer)
    assert not isinstance(_gatherer("ics"), ChangeProbeGatherer)
