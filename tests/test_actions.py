"""Tests for app.services.actions (the shared admin operations)."""
#region: imports
import pytest
from sqlmodel import SQLModel, create_engine

from app.schema import CategoryRule
from app.services import actions
from app.services.actions import ActionError
#endregion


def _engine(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'actions.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("app.services.actions.engine", engine)
    monkeypatch.setattr("app.db.engine", engine)
    monkeypatch.setattr("app.ingest.engine", engine)
    return engine


#region: parsing
def test_resolve_source_spec_manual_sentinel(monkeypatch):
    cfg = actions.resolve_source_spec({"source": "manual", "gatherer": "elfsight", "url": "https://x"})
    assert cfg is not None
    assert cfg.gatherer == "elfsight"
    assert cfg.url == "https://x"


def test_resolve_source_spec_missing_fields(monkeypatch):
    assert actions.resolve_source_spec({"source": "manual"}) is None


def test_parse_rules_single_dict():
    rules = actions.parse_rules({"rules": {"mode": "assign", "categories": ["art"]}})
    assert rules == [CategoryRule(mode="assign", categories=["art"])]


def test_parse_rules_none():
    assert actions.parse_rules({}) is None
#endregion


#region: write actions
def test_retag_requires_from(tmp_path, monkeypatch):
    _engine(tmp_path, monkeypatch)
    with pytest.raises(ActionError):
        actions.retag("", "external:art")


def test_wipe_challenge_flow(tmp_path, monkeypatch):
    _engine(tmp_path, monkeypatch)
    challenge = actions.wipe_begin()
    assert isinstance(challenge, str) and challenge

    with pytest.raises(ActionError):
        actions.wipe_confirm("nope")

    result = actions.wipe_confirm(challenge)
    assert result == {"events": 0, "sources": 0}

    # challenge is consumed — a second use fails
    with pytest.raises(ActionError):
        actions.wipe_confirm(challenge)
#endregion
