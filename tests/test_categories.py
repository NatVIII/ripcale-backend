"""Tests for category classification (F46)."""
#region: imports
from app.intake import IntakeSettings, save
from app.services.categories import DEFAULT_CLASS, EXTERNAL, INTAKE, category_class
#endregion


def _configure(tmp_path, monkeypatch, classes):
    from app.config import settings

    monkeypatch.setattr(settings, "intake_file", str(tmp_path / "intake.yaml"))
    save(IntakeSettings(category_definitions=classes))


def test_category_class_returns_external(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, {"external": ["art", "music"]})
    assert category_class("art") == EXTERNAL
    assert category_class("music") == EXTERNAL


def test_category_class_returns_intake(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, {"intake": ["art-exhibition"]})
    assert category_class("art-exhibition") == INTAKE


def test_category_class_defaults_to_intake(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, {"external": ["art"]})
    assert category_class("unlisted-thing") == INTAKE
    assert DEFAULT_CLASS == INTAKE


def test_category_class_empty_registry(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, {})
    assert category_class("anything") == INTAKE


def test_category_definitions_round_trip(tmp_path, monkeypatch):
    from app.config import settings
    from app.intake import load

    path = tmp_path / "intake.yaml"
    monkeypatch.setattr(settings, "intake_file", str(path))
    save(IntakeSettings(category_definitions={"external": ["art"], "intake": ["raw-stuff"]}))

    assert load().category_definitions == {"external": ["art"], "intake": ["raw-stuff"]}
    assert category_class("art") == EXTERNAL
    assert category_class("raw-stuff") == INTAKE
#endregion
