"""Shared test fixtures."""
#region: imports
import pytest
#endregion


@pytest.fixture
def session_headers():
    """A valid session cookie header (authenticates the /debug dashboard)."""
    from app.services import auth

    return {"Cookie": f"ripcale_session={auth.create_session('admin')}"}


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """Point `settings.data_dir` and `settings.intake_file` at a temp dir so
    tests never touch real `data/` or `intake.yaml`. Also set a placeholder
    `api_token` so valid-config checks don't report the "API disabled" warning."""
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr("app.config.settings.intake_file", str(tmp_path / "intake.yaml"))
    monkeypatch.setattr("app.config.settings.api_token", "test-token")
