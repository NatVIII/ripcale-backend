"""Tests for the intake settings store (app/intake.py)."""
#region: imports
from app.intake import IntakeSettings, load, save
from app.schema import CategoryRule, GathererConfig, SourceConfig
#endregion


def test_load_missing_file_returns_defaults(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "intake_file", str(tmp_path / "missing.yaml"))
    intake = load()
    assert intake.sources == []
    assert intake.gatherers == {}
    assert intake.category_symlinks == {}
    assert intake.category_definitions == {}
    assert intake.rules == []


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    from app.config import settings

    path = tmp_path / "intake.yaml"
    monkeypatch.setattr(settings, "intake_file", str(path))

    save(
        IntakeSettings(
            sources=[SourceConfig(name="S", gatherer="elfsight", url="https://x")],
            gatherers={"elfsight": GathererConfig(priority=5)},
            category_symlinks={"art-exhibition": "art"},
            category_definitions={"external": ["art"]},
            rules=[CategoryRule(mode="assign", categories=["community"])],
        )
    )

    intake = load()
    assert [s.name for s in intake.sources] == ["S"]
    assert intake.gatherers["elfsight"].priority == 5
    assert intake.category_symlinks == {"art-exhibition": "art"}
    assert intake.category_definitions == {"external": ["art"]}
    assert [r.mode for r in intake.rules] == ["assign"]


def test_save_is_atomic_and_leaves_no_tmp(tmp_path, monkeypatch):
    from app.config import settings

    path = tmp_path / "intake.yaml"
    monkeypatch.setattr(settings, "intake_file", str(path))

    save(IntakeSettings(sources=[SourceConfig(name="S", gatherer="elfsight", url="https://x")]))

    assert path.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_load_revalidates_on_mtime_change(tmp_path, monkeypatch):
    from app.config import settings

    path = tmp_path / "intake.yaml"
    monkeypatch.setattr(settings, "intake_file", str(path))

    save(IntakeSettings(category_symlinks={"a": "b"}))
    assert load().category_symlinks == {"a": "b"}

    save(IntakeSettings(category_symlinks={"c": "d"}))
    assert load().category_symlinks == {"c": "d"}
#endregion
