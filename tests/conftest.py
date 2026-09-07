"""Shared test fixtures."""
#region: imports
import pytest
#endregion


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """Point `settings.data_dir` and `settings.intake_file` at a temp dir so
    tests never touch real `data/` or `intake.yaml`."""
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr("app.config.settings.intake_file", str(tmp_path / "intake.yaml"))
