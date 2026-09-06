"""Shared test fixtures."""
#region: imports
import pytest
#endregion


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """Point `settings.data_dir` at a temp dir so tests never touch real `data/`."""
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
